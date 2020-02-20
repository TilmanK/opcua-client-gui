"""Attribute Widget to control Attribute view and model."""
import logging
from typing import Optional, Dict, List

from PyQt5.QtCore import QObject, QSettings, QModelIndex, pyqtSlot, Qt, QPoint
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import QTreeView, QHeaderView, QMenu, QApplication
from asyncua.common.ua_utils import val_to_string
from asyncua.sync import Node
from asyncua.ua import DataValue, AttributeIds, VariantType, Argument


class AttributeWidget(QObject):
    """Controller for the AttributeView."""

    LABELS = ['Attribute', 'Value', 'DataType']

    def __init__(self, view: QTreeView, parent: QObject = None):
        """Create a new AttributeWidget controller for view and model."""
        super(AttributeWidget, self).__init__(parent)

        self._current_node = Optional[Node]

        self._view = view
        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(AttributeWidget.LABELS)

        self._load_state()

        self._view.header().setSectionResizeMode(QHeaderView.Interactive)
        self._view.setModel(self._model)

        self._view.expanded.connect(self.item_expanded)
        self._view.collapsed.connect(self.item_collapsed)

        self._view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._show_context_menu)

        # Todo: Handle Edit

    @pyqtSlot(QPoint, name="_show_context_menu")
    def _show_context_menu(self, position: QPoint) -> None:
        index = self._view.indexAt(position)
        if not index.isValid():
            logging.debug("Context menu requested for invalid position.")
        item = self._model.itemFromIndex(index)
        if item:
            global_pos = self._view.viewport().mapToGlobal(position)
            menu = QMenu()
            copy_action = menu.addAction(self.tr("&Copy Value"))
            copy_action.triggered.connect(self.copy_value)
            menu.exec(global_pos)

    @pyqtSlot(name="copy_value")
    def copy_value(self) -> None:
        """Copy the value of the currently selected row."""
        idx = self._view.currentIndex()
        idx = idx.siblingAtColumn(1)
        item = self._model.itemFromIndex(idx)
        QApplication.clipboard().setText(item.text())

    @pyqtSlot(QModelIndex, name="item_expanded")
    def item_expanded(self, index: QModelIndex) -> None:
        """Handle an item being expanded."""
        index = index.siblingAtColumn(1)
        item = self._model.itemFromIndex(index)
        item.setText("")

    @pyqtSlot(QModelIndex, name="item_collapsed")
    def item_collapsed(self, index: QModelIndex) -> None:
        """Handle an item being collapsed."""
        item = self._model.itemFromIndex(index.siblingAtColumn(1))
        data = item.data(Qt.UserRole)
        item.setText(val_to_string(data))

    def show_attributes(self, node: Node) -> None:
        """Show the attributes for the given Node."""
        logging.debug("Showing attributes for Node: %s", node)
        self.clear()
        self._current_node = node
        if node:
            for attr, value in sorted(self._get_all_attributes().items(),
                                      key=lambda x: x[0].name):
                self._model.appendRow(self._get_attr_rows(attr, value))

    def _get_attr_rows(self, attr: AttributeIds, value: DataValue)\
            -> List[QStandardItem]:
        """Return a row of QStandardItems representing an Attribute."""
        logging.debug("Generating row for attr %s and value %s", attr, value)
        name_item = QStandardItem(attr.name)
        if attr == AttributeIds.Value:
            for row in self._get_value_rows(attr, value):
                name_item.appendRow(row)
        value_item = QStandardItem(val_to_string(value))
        value_item.setData(value.Value.Value, Qt.UserRole)
        type_item = QStandardItem(value.Value.VariantType.name)
        return [name_item, value_item, type_item]

    def _get_value_rows(self, attr: AttributeIds, value: DataValue)\
            -> List[List[QStandardItem]]:
        """Return a list of rows of QStandardItems representing a Value."""
        rows = []
        name_item = QStandardItem(attr.name)
        if isinstance(value.Value.Value, list):
            for row in self._get_list_rows(value):
                name_item.appendRow(row)
        elif value.Value.VariantType == VariantType.ExtensionObject:
            for row in self._get_extension_rows(value.Value.Value):
                name_item.appendRow(row)
        value_item = QStandardItem(val_to_string(value))
        value_item.setData(value, Qt.UserRole)
        rows.append([name_item,
                     value_item,
                     QStandardItem(value.Value.VariantType.name)])
        d_str = VariantType.DateTime.name
        rows.append([QStandardItem("Server Timestamp"),
                     QStandardItem(str(value.ServerTimestamp)),
                     QStandardItem(d_str)])
        rows.append([QStandardItem("Source Timestamp"),
                     QStandardItem(str(value.SourceTimestamp)),
                     QStandardItem(d_str)])
        return rows

    def _get_list_rows(self, value: DataValue)\
            -> List[List[QStandardItem]]:
        """Return a list of rows of QStandardItems representing a list."""
        rows = []
        for val in value.Value.Value:
            name_item = QStandardItem(str(value.Value.Value.index(val)))
            if value.Value.VariantType == VariantType.ExtensionObject:
                for row in self._get_extension_rows(val):
                    name_item.appendRow(row)
            value_item = QStandardItem(str(val))
            value_item.setData(value.Value.Value, Qt.UserRole)
            type_item = QStandardItem(value.Value.VariantType.name)
            rows.append([name_item, value_item, type_item])
        return rows

    @staticmethod
    def _get_extension_rows(value: Argument)-> List[List[QStandardItem]]:
        """Return a list of rows of QStandardItems for an ExtensionObject."""
        rows = []
        for arg_name, arg_type in value.ua_types:
            name_item = QStandardItem(arg_name)
            attr_val = getattr(value, arg_name)
            value_item = QStandardItem(val_to_string(attr_val))
            value_item.setData(attr_val, Qt.UserRole)
            type_item = QStandardItem(arg_type)
            rows.append([name_item, value_item, type_item])
        return rows

    def _get_all_attributes(self) -> Dict[AttributeIds, DataValue]:
        """Get all attributes for the currently set node."""
        values = self._current_node.get_attributes(AttributeIds)
        result = {AttributeIds(idx + 1): value
                  for idx, value in enumerate(values)
                  if value.StatusCode.is_good()}
        return result

    def clear(self) -> None:
        """Clear the model data."""
        # Todo: This is probably not efficient, refactor
        self._model.removeRows(0, self._model.rowCount())

    def _load_state(self) -> None:
        """Load the state of the header from QSettings."""
        logging.debug("Restoring state from QSettings.")
        state = QSettings().value("WindowState/attrs_widget_state", None)
        if state is not None:
            self._view.header().restoreState(state)
        else:
            logging.debug("No state was saved in QSettings")

    def save_state(self) -> None:
        """Save the state of the header to QSettings."""
        QSettings().setValue("WindowState/attrs_widget_state",
                             self._view.header().saveState())
