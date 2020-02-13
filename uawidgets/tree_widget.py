"""TreeWidget and TreeView definitions."""
import logging
from typing import Optional, List, Iterable, Dict

from PyQt5.QtCore import QMimeData, QObject, Qt, QSettings, QModelIndex
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon
from PyQt5.QtWidgets import QApplication, QTreeView, QHeaderView

from asyncua.ua import ReferenceDescription, ObjectIds, TwoByteNodeId, \
    NodeClass
from asyncua.sync import Node


class TreeWidget(QObject):
    """TreeWidget controlling TreeViewModel and TreeView."""

    HEADER_LABELS = ['DisplayName', "BrowseName", 'NodeId']

    def __init__(self, view: QTreeView) -> None:
        """Create a new TreeWidget."""
        QObject.__init__(self, view)
        self._view = view
        self._model = TreeViewModel()
        self._view.setModel(self._model)

        self._model.setHorizontalHeaderLabels(TreeWidget.HEADER_LABELS)
        self._view.header().setSectionResizeMode(QHeaderView.Interactive)
        self._load_state()

    def _load_state(self) -> None:
        """Load the header state from the settings and set it."""
        try:
            self._view.header().restoreState(
                QSettings().value("tree_widget_state", None))
        except TypeError:
            logging.info("Could not restore state from QSettings.")

    def save_state(self) -> None:
        """Save the header state to the settings."""
        QSettings().setValue("tree_widget_state",
                             self._view.header().saveState())

    def clear(self) -> None:
        """Clear the model."""
        self._model.clear()

    def set_root_node(self, node: Node) -> None:
        """Set the root node initializing the model."""
        self._model.clear()
        self._model.set_root_node(node)
        self._view.expandToDepth(0)

    def copy_path(self) -> None:
        """Copy the current path to the Clipboard."""
        path = self.get_current_path()
        path_str = ",".join(path)
        QApplication.clipboard().setText(path_str)

    def expand_to_node(self, node: Node) -> None:
        """Expand tree until given node and select it."""
        index = self._model.match(self._model.index(0, 0), Qt.UserRole,
                                  node, 1, Qt.MatchExactly)[0]
        self._view.setExpanded(index, True)
        self._view.setCurrentIndex(index)
        self._view.activated.emit(index)

    def copy_nodeid(self) -> None:
        """Copy the node id of the current node."""
        node = self.get_current_node()
        # the method should never be called if there is no current node
        assert node
        QApplication.clipboard().setText(node.nodeid.to_string())

    def get_current_path(self) -> List[str]:
        """Get the path of the current index."""
        idx = self._view.currentIndex()
        idx = idx.sibling(idx.row(), 0)
        item = self._model.itemFromIndex(idx)
        path: List[str] = []
        while item and item.data(Qt.UserRole):
            node = item.data(Qt.UserRole)
            name = node.get_browse_name().to_string()
            path.insert(0, name)
            item = item.parent()
        return path

    def get_current_node(self) -> Node:
        """Get the currently selected node."""
        index = self._view.currentIndex()
        index = index.sibling(index.row(), 0)
        node = self._model.itemFromIndex(index).data(Qt.UserRole)
        logging.debug("Got node for Index: %s", node)
        return node


class TreeViewModel(QStandardItemModel):
    """Tree view model containing Nodes of the connected server."""

    # pylint: disable=invalid-name
    def __init__(self) -> None:
        """Create a new TreeViewModel."""
        super(TreeViewModel, self).__init__()
        self._fetched: List[Node] = []
        self._descr_cache: Dict[Node, ReferenceDescription] = {}
        self._root_node: Optional[Node] = None

    def clear(self) -> None:
        """Remove all items and reset the header."""
        logging.debug("Clearing Model")
        self.removeRows(0, self.rowCount())
        self._fetched = []
        self._descr_cache.clear()
        self._root_node = None

    def set_root_node(self, node: Node) -> None:
        """Set the root node for the model."""
        self._root_node = node
        description = self._get_node_desc(node)
        item = self._create_items(description, node)
        self.appendRow(item)

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

    def _add_item_with_parent(self, desc: ReferenceDescription,
                              parent: QStandardItem) -> None:
        """Add an item to the model with the given parent."""
        parent_node = parent.data(Qt.UserRole)
        node = parent_node.get_child(desc.BrowseName.to_string())
        item = self._create_items(desc, node)
        parent.appendRow(item)

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
            del self._descr_cache[node]
        except ValueError:
            pass

    def canFetchMore(self, parent: QModelIndex) -> bool:  # nopep8
        """Return if more items can be fetched for the given parent."""
        if not parent.isValid():
            return False
        node = self.itemFromIndex(parent).data(Qt.UserRole)
        if node not in self._fetched:
            return True
        return False

    def hasChildren(self, idx: QModelIndex = QModelIndex()) -> bool:  # nopep8
        """Return if the given index has children."""
        if not idx.isValid():
            # if the index isn't valid, it's the root of the TreeView
            return bool(self._root_node)
        node = self.itemFromIndex(idx).data(Qt.UserRole)
        try:
            return bool(self._descr_cache[node])
        except KeyError:
            descriptions = node.get_children_descriptions()
            self._descr_cache[node] = descriptions
            return bool(descriptions)

    def fetchMore(self, idx: QModelIndex) -> None:  # nopep8
        """Fetch and publish the children for the given index."""
        parent = self.itemFromIndex(idx)
        node = parent.data(Qt.UserRole)
        self._fetched.append(node)
        descriptions = node.get_children_descriptions()
        descriptions.sort(key=lambda x: x.BrowseName)
        self._descr_cache[node] = descriptions
        for desc in descriptions:
            self._add_item_with_parent(desc, parent)

    def mimeData(self, indexes: Iterable[QModelIndex]) -> QMimeData:  # nopep8
        """Return a QMimeData object for the given indexes."""
        items = [self.itemFromIndex(idx) for idx in indexes]
        nodes = [item.data(Qt.UserRole) for item in items]
        node_ids = [node.nodeid.to_string() for node in nodes if node]
        mdata = QMimeData()
        mdata.setText(", ".join(node_ids))
        return mdata
