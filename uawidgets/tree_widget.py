import logging
from typing import Optional, List, Iterable

from PyQt5.QtCore import pyqtSignal, QMimeData, QObject, Qt, QSettings, \
    QModelIndex
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon
from PyQt5.QtWidgets import QApplication, QAbstractItemView, QAction

from asyncua.ua import ReferenceDescription, ObjectIds, TwoByteNodeId, \
    NodeClass
from asyncua.sync import Node
from asyncua.ua import UaError


class TreeWidget(QObject):

    error = pyqtSignal(Exception)
    HEADER_LABELS = ['DisplayName', "BrowseName", 'NodeId']

    def __init__(self, view):
        QObject.__init__(self, view)
        self.view = view
        self.model = TreeViewModel()
        self.model.clear()
        self.view.setModel(self.model)

        #self.view.setUniformRowHeights(True)
        self.model.setHorizontalHeaderLabels(TreeWidget.HEADER_LABELS)
        self.view.header().setSectionResizeMode(0)
        self.view.header().setStretchLastSection(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.settings = QSettings()
        state = self.settings.value("tree_widget_state", None)
        if state is not None:
            self.view.header().restoreState(state)

        # Todo: I can't see where this is used, should be removed?
        self.actionReload = QAction("Reload", self)
        self.actionReload.triggered.connect(self.reload_current)

    def save_state(self):
        self.settings.setValue("tree_widget_state", self.view.header().saveState())

    def clear(self):
        self.model.clear()

    def set_root_node(self, node):
        self.model.clear()
        self.model.set_root_node(node)
        self.view.expandToDepth(0)

    def copy_path(self):
        path = self.get_current_path()
        path_str = ",".join(path)
        QApplication.clipboard().setText(path_str)

    def expand_current_node(self, expand=True):
        idx = self.view.currentIndex()
        self.view.setExpanded(idx, expand)

    def expand_to_node(self, node):
        """
        Expand tree until given node and select it
        """
        if isinstance(node, str):
            idxlist = self.model.match(self.model.index(0, 0), Qt.DisplayRole, node, 1, Qt.MatchExactly|Qt.MatchRecursive)
            if not idxlist:
                raise ValueError(f"Node {node} not found in tree")
            node = self.model.data(idxlist[0], Qt.UserRole)
        path = node.get_path()
        for node in path:
            # FIXME: this would be the correct way if it would work
            #idxlist = self.model.match(self.model.index(0, 0), Qt.UserRole, node.node, 2, Qt.MatchExactly|Qt.MatchRecursive)
            try:
                text = node.get_display_name().Text
            except UaError as ex:
                return
            idxlist = self.model.match(self.model.index(0, 0), Qt.DisplayRole, text, 1, Qt.MatchExactly|Qt.MatchRecursive)
            if idxlist:
                idx = idxlist[0]
                self.view.setExpanded(idx, True)
                self.view.setCurrentIndex(idx)
                self.view.activated.emit(idx)
            else:
                print(f"While expanding tree, Could not find node {node} in tree view, this might be OK")

    def copy_nodeid(self):
        node = self.get_current_node()
        text = node.nodeid.to_string()
        QApplication.clipboard().setText(text)

    def get_current_path(self):
        idx = self.view.currentIndex()
        idx = idx.sibling(idx.row(), 0)
        it = self.model.itemFromIndex(idx)
        path = []
        while it and it.data(Qt.UserRole):
            node = it.data(Qt.UserRole)
            name = node.get_browse_name().to_string()
            path.insert(0, name)
            it = it.parent()
        return path

    def update_browse_name_current_item(self, bname):
        idx = self.view.currentIndex()
        idx = idx.sibling(idx.row(), 1)
        it = self.model.itemFromIndex(idx)
        it.setText(bname.to_string())

    def update_display_name_current_item(self, dname):
        idx = self.view.currentIndex()
        idx = idx.sibling(idx.row(), 0)
        it = self.model.itemFromIndex(idx)
        it.setText(dname.Text)

    def reload_current(self):
        idx = self.view.currentIndex()
        idx = idx.sibling(idx.row(), 0)
        it = self.model.itemFromIndex(idx)
        if not it:
            return None
        self.reload(it)

    def reload(self, item=None):
        if item is None:
            item = self.model.item(0, 0)
            node = item.data(Qt.UserRole)
        for _ in range(item.rowCount()):
            child_it = item.child(0, 0)
            node = child_it.data(Qt.UserRole)
            if node:
                self.model.reset_cache(node)
            item.takeRow(0)
        node = item.data(Qt.UserRole)
        if node:
            self.model.reset_cache(node)
            idx = self.model.indexFromItem(item)
            #if self.view.isExpanded(idx):
            #self.view.setExpanded(idx, True)

    def remove_current_item(self) -> None:
        """Removes the current item from the model."""
        idx = self.view.currentIndex()
        self.model.removeRow(idx.row(), idx.parent())

    def get_current_node(self) -> Optional[Node]:
        idx = self.view.currentIndex()
        msg = 'Current Index: row: %s, col: %s, parent: %s, parent_valid: %s'
        logging.debug(msg, idx.row(), idx.column(), idx.parent(),
                      idx.isValid())
        node = self.model.itemFromIndex(idx).data(Qt.UserRole)
        logging.debug("Got node for Index: %s", node)
        return node


class TreeViewModel(QStandardItemModel):
    """Tree view model containing Nodes of the connected server."""

    # pylint: disable=invalid-name
    def __init__(self) -> None:
        """Create a new TreeViewModel."""
        super(TreeViewModel, self).__init__()
        self._fetched: List[Node] = []

    def clear(self) -> None:
        """Remove all items and reset the header."""
        self.removeRows(0, self.rowCount())
        self._fetched = []

    def set_root_node(self, node: Node) -> None:
        """Set the root node for the model."""
        assert not self._fetched
        description = self._get_node_desc(node)
        self.add_item_by_node(description, node=node)

    @staticmethod
    def _get_node_desc(node: Node) -> ReferenceDescription:
        """Get the ReferenceDescription of a node."""
        description = ReferenceDescription()
        description.DisplayName = node.get_display_name()
        description.BrowseName = node.get_browse_name()
        description.NodeId = node.nodeid
        description.NodeClass = node.get_node_class()
        description.TypeDefinition = TwoByteNodeId(ObjectIds.FolderType)
        return description

    def add_item_with_parent(self, desc: ReferenceDescription,
                             parent: QStandardItem) -> None:
        """Add an item to the model with the given parent."""
        parent_node = parent.data(Qt.UserRole)
        node = parent_node.get_child(desc.BrowseName.to_string())
        item = self._create_items(desc, node)
        parent.appendRow(item)

    def add_item_by_node(self, desc: ReferenceDescription, node: Node) -> None:
        """Add an item to the model."""
        item = self._create_items(desc, node)
        self.appendRow(item)

    def _create_items(self, desc: ReferenceDescription, node: Node)\
            -> List[QStandardItem]:
        """Create a list of items from a description and a node."""
        dname = desc.DisplayName.to_string()
        bname = desc.BrowseName.to_string()
        nodeid = desc.NodeId.to_string()
        items = [QStandardItem(dname),
                 QStandardItem(bname),
                 QStandardItem(nodeid)]
        self._add_icon_to_item(desc, items[0])
        items[0].setData(node, Qt.UserRole)
        return items

    @staticmethod
    def _add_icon_to_item(desc: ReferenceDescription, item: QStandardItem)\
            -> None:
        """Add an icon to the item based on the description."""
        if desc.NodeClass == NodeClass.Object:
            if desc.TypeDefinition == TwoByteNodeId(ObjectIds.FolderType):
                item.setIcon(QIcon("uawidgets/folder.svg"))
            else:
                item.setIcon(QIcon("uawidgets/object.svg"))
        elif desc.NodeClass == NodeClass.Variable:
            if desc.TypeDefinition == TwoByteNodeId(ObjectIds.PropertyType):
                item.setIcon(QIcon("uawidgets/property.svg"))
            else:
                item.setIcon(QIcon("uawidgets/variable.svg"))
        elif desc.NodeClass == NodeClass.Method:
            item.setIcon(QIcon("uawidgets/method.svg"))
        elif desc.NodeClass == NodeClass.ObjectType:
            item.setIcon(QIcon("uawidgets/object_type.svg"))
        elif desc.NodeClass == NodeClass.VariableType:
            item.setIcon(QIcon("uawidgets/variable_type.svg"))
        elif desc.NodeClass == NodeClass.DataType:
            item.setIcon(QIcon("uawidgets/data_type.svg"))
        elif desc.NodeClass == NodeClass.ReferenceType:
            item.setIcon(QIcon("uawidgets/reference_type.svg"))
        else:
            logging.warning("Could not set item for desc %s", desc)

    def reset_cache(self, node: Node) -> None:
        """Reset the internal cache for the given node."""
        try:
            self._fetched.remove(node)
        except ValueError:
            pass

    def canFetchMore(self, parent: QModelIndex) -> bool:
        """Return if more items can be fetched for the given parent."""
        if not parent.isValid():
            return False
        node = self.itemFromIndex(parent).data(Qt.UserRole)
        if node not in self._fetched:
            self._fetched.append(node)
            return True
        return False

    def hasChildren(self, idx: QModelIndex = QModelIndex()) -> bool:
        """Return if the given index has children."""
        if not idx.isValid():
            # if the index isn't valid, it's the root of the TreeView
            return True
        node = self.itemFromIndex(idx).data(Qt.UserRole)
        # Todo: Refactor to not cause a request every time method is called
        return bool(node.get_children_descriptions())

    def fetchMore(self, idx: QModelIndex) -> None:
        """Fetch and publish the children for the given index."""
        parent = self.itemFromIndex(idx)
        node = parent.data(Qt.UserRole)
        descriptions = node.get_children_descriptions()
        descriptions.sort(key=lambda x: x.BrowseName)
        for desc in descriptions:
            self.add_item_with_parent(desc, parent)

    def mimeData(self, indexes: Iterable[QModelIndex]) -> QMimeData:
        """Return a QMimeData object for the given indexes."""
        items = [self.itemFromIndex(idx) for idx in indexes]
        nodes = [item.data(Qt.UserRole) for item in items]
        node_ids = [node.nodeid.to_string() for node in nodes if node]
        mdata = QMimeData()
        mdata.setText(", ".join(node_ids))
        return mdata
