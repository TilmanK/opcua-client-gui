#! /usr/bin/env python3
import os
import sys
import traceback

from datetime import datetime
import logging
from typing import List, Optional

from PyQt5.QtCore import pyqtSignal, QTimer, Qt, QObject, QSettings, \
    QItemSelection, QCoreApplication, pyqtSlot, QPoint
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon, QCloseEvent
from PyQt5.QtWidgets import QMainWindow, QWidget, QApplication, \
    QMenu, QMessageBox, QAction

from asyncua.sync import ua
from asyncua.sync import Node

from uaclient.uaclient import UaClient
from uaclient.mainwindow_ui import Ui_MainWindow
from uaclient.connection_dialog import ConnectionDialog
from uaclient.graphwidget import GraphUI

from uawidgets.attrs_widget import AttrsWidget
from uawidgets.tree_widget import TreeWidget
from uawidgets.refs_widget import RefsWidget
from uawidgets.call_method_dialog import CallMethodDialog


logger = logging.getLogger(__name__)


class DataChangeHandler(QObject):
    data_change_fired = pyqtSignal(object, str, str)

    def datachange_notification(self, node, val, data):
        if data.monitored_item.Value.SourceTimestamp:
            dato = data.monitored_item.Value.SourceTimestamp.isoformat()
        elif data.monitored_item.Value.ServerTimestamp:
            dato = data.monitored_item.Value.ServerTimestamp.isoformat()
        else:
            dato = datetime.now().isoformat()
        self.data_change_fired.emit(node, str(val), dato)


class EventHandler(QObject):
    event_fired = pyqtSignal(object)

    def event_notification(self, event):
        self.event_fired.emit(event)


class EventUI(object):

    def __init__(self, window, uaclient):
        self.window = window
        self.uaclient = uaclient
        self._handler = EventHandler()
        self._subscribed_nodes = []  # FIXME: not really needed
        self.model = QStandardItemModel()
        self.window.ui.evView.setModel(self.model)
        self.window.ui.actionSubscribeEvent.triggered.connect(self._subscribe)
        self.window.ui.actionUnsubscribeEvents.triggered.connect(self._unsubscribe)
        # context menu
        self.window.addAction(self.window.ui.actionSubscribeEvent)
        self.window.addAction(self.window.ui.actionUnsubscribeEvents)
        self.window.addAction(self.window.ui.actionAddToGraph)
        self._handler.event_fired.connect(self._update_event_model, type=Qt.QueuedConnection)

        # accept drops
        self.model.canDropMimeData = self.canDropMimeData
        self.model.dropMimeData = self.dropMimeData

    def canDropMimeData(self, mdata, action, row, column, parent):
        return True

    def show_error(self, *args):
        self.window.show_error(*args)

    def dropMimeData(self, mdata, action, row, column, parent):
        node = self.uaclient.client.get_node(mdata.text())
        self._subscribe(node)
        return True

    def clear(self):
        self._subscribed_nodes = []
        self.model.clear()

    def _subscribe(self, node=None):
        logger.info("Subscribing to %s", node)
        if not node:
            node = self.window.get_current_node()
            if node is None:
                return
        if node in self._subscribed_nodes:
            logger.info("already subscribed to event for node: %s", node)
            return
        logger.info("Subscribing to events for %s", node)
        self.window.ui.evDockWidget.raise_()
        try:
            self.uaclient.subscribe_events(node, self._handler)
        except Exception as ex:
            self.window.show_error(ex)
            raise
        else:
            self._subscribed_nodes.append(node)

    def _unsubscribe(self):
        node = self.window.get_current_node()
        if node is None:
            return
        self._subscribed_nodes.remove(node)
        self.uaclient.unsubscribe_events(node)

    def _update_event_model(self, event):
        self.model.appendRow([QStandardItem(str(event))])


class DataChangeUI(object):

    def __init__(self, window, uaclient):
        self.window = window
        self.uaclient = uaclient
        self._subhandler = DataChangeHandler()
        self._subscribed_nodes = []
        self.model = QStandardItemModel()
        self.window.ui.subView.setModel(self.model)
        self.window.ui.subView.horizontalHeader().setSectionResizeMode(1)

        self.window.ui.actionSubscribeDataChange.triggered.connect(self._subscribe)
        self.window.ui.actionUnsubscribeDataChange.triggered.connect(self._unsubscribe)

        # populate contextual menu
        self.window.addAction(self.window.ui.actionSubscribeDataChange)
        self.window.addAction(self.window.ui.actionUnsubscribeDataChange)

        # handle subscriptions
        self._subhandler.data_change_fired.connect(self._update_subscription_model, type=Qt.QueuedConnection)
        
        # accept drops
        self.model.canDropMimeData = self.canDropMimeData
        self.model.dropMimeData = self.dropMimeData

    def canDropMimeData(self, mdata, action, row, column, parent):
        return True

    def dropMimeData(self, mdata, action, row, column, parent):
        node = self.uaclient.client.get_node(mdata.text())
        self._subscribe(node)
        return True

    def clear(self):
        self._subscribed_nodes = []
        self.model.clear()

    def show_error(self, *args):
        self.window.show_error(*args)

    def _subscribe(self, node=None):
        if not isinstance(node, Node):
            node = self.window.get_current_node()
            if node is None:
                return
        if node in self._subscribed_nodes:
            logger.warning("allready subscribed to node: %s ", node)
            return
        self.model.setHorizontalHeaderLabels(["DisplayName", "Value", "Timestamp"])
        text = str(node.get_display_name().Text)
        row = [QStandardItem(text), QStandardItem("No Data yet"), QStandardItem("")]
        row[0].setData(node)
        self.model.appendRow(row)
        self._subscribed_nodes.append(node)
        self.window.ui.subDockWidget.raise_()
        try:
            self.uaclient.subscribe_datachange(node, self._subhandler)
        except Exception as ex:
            self.window.show_error(ex)
            idx = self.model.indexFromItem(row[0])
            self.model.takeRow(idx.row())
            raise

    def _unsubscribe(self):
        node = self.window.get_current_node()
        if node is None:
            return
        self.uaclient.unsubscribe_datachange(node)
        self._subscribed_nodes.remove(node)
        i = 0
        while self.model.item(i):
            item = self.model.item(i)
            if item.data() == node:
                self.model.removeRow(i)
            i += 1

    def _update_subscription_model(self, node, value, timestamp):
        i = 0
        while self.model.item(i):
            item = self.model.item(i)
            if item.data() == node:
                it = self.model.item(i, 1)
                it.setText(value)
                it_ts = self.model.item(i, 2)
                it_ts.setText(timestamp)
            i += 1


class Window(QMainWindow):
    """Main window for FreeOpcUa Client."""

    def __init__(self) -> None:
        """Create a new Window."""
        QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowIcon(QIcon(":/network.svg"))

        # fix stuff impossible to do in Qt Desinger
        # remove dock titlebar for addressbar
        self.ui.addrDockWidget.setTitleBarWidget(QWidget())
        # tabify some docks
        self.tabifyDockWidget(self.ui.evDockWidget, self.ui.subDockWidget)
        self.tabifyDockWidget(self.ui.subDockWidget, self.ui.refDockWidget)
        self.tabifyDockWidget(self.ui.refDockWidget, self.ui.graphDockWidget)

        # we only show statusbar in case of errors
        self.ui.statusBar.hide()

        # setup QSettings for application and get a settings object
        QCoreApplication.setOrganizationName("FreeOpcUa")
        QCoreApplication.setApplicationName("OpcUaClient")
        self._settings = QSettings()

        adr_default = ["opc.tcp://localhost:4840",
                       "opc.tcp://localhost:53530/OPCUA/SimulationServer/"]
        self._address_list: List[str] = self._settings.value("address_list",
                                                             adr_default)
        logging.debug("Address list: %s", self._address_list)
        self._address_list_max_count: int = \
            int(self._settings.value("address_list_max_count", 10))

        # init widgets
        self.ui.addrComboBox.addItems(self._address_list)

        self.ua_client: UaClient = UaClient()

        self.tree_ui: TreeWidget = TreeWidget(self.ui.treeView)
        self.tree_ui.error.connect(self.show_error)
        self.setup_context_menu_tree()
        self.ui.treeView.selectionModel().currentChanged.connect(
            self.update_actions_state)

        self._refs_ui = RefsWidget(self.ui.refView)
        self._refs_ui.error.connect(self.show_error)
        self._attrs_ui = AttrsWidget(self.ui.attrView)
        self._attrs_ui.error.connect(self.show_error)
        self._datachange_ui = DataChangeUI(self, self.ua_client)
        self._event_ui = EventUI(self, self.ua_client)
        self._graph_ui = GraphUI(self, self.ua_client)

        self.ui.addrComboBox.currentTextChanged.connect(self._uri_changed)
        # force update for current value at startup
        self._uri_changed(self.ui.addrComboBox.currentText())

        self.ui.treeView.selectionModel().selectionChanged.connect(
            self.show_refs)
        self.ui.actionCopyPath.triggered.connect(self.tree_ui.copy_path)
        self.ui.actionCopyNodeId.triggered.connect(self.tree_ui.copy_nodeid)
        self.ui.actionCall.triggered.connect(self.call_method)

        self.ui.treeView.selectionModel().selectionChanged.connect(
            self.show_attrs)
        self.ui.attrRefreshButton.clicked.connect(self.show_attrs)

        self._restore_states()

        self.ui.connectButton.clicked.connect(self.connect)
        self.ui.disconnectButton.clicked.connect(self.disconnect)

        self.ui.actionConnect.triggered.connect(self.connect)
        self.ui.actionDisconnect.triggered.connect(self.disconnect)

        self.ui.connectOptionButton.clicked.connect(
            self.show_connection_dialog)

    def _restore_states(self) -> None:
        """Restore the ui state as saved in the settings."""
        try:
            self.restoreGeometry(self._settings.value("geometry", None))
        except TypeError:
            logging.debug("No geometry was stored - cannot restore")
        try:
            self.restoreState(self._settings.value("state", None))
        except TypeError:
            logging.debug("No state was stored - cannot restore")

    @pyqtSlot(str, name="_uri_changed")
    def _uri_changed(self, uri: str) -> None:
        self.ua_client.load_security_settings(uri)

    @pyqtSlot(name="show_connection_dialog")
    def show_connection_dialog(self) -> None:
        """Show the connection dialog and set the results if confirmed."""
        dia = ConnectionDialog(self, self.ui.addrComboBox.currentText())
        dia.security_mode = self.ua_client.security_mode
        dia.security_policy = self.ua_client.security_policy
        dia.certificate_path = self.ua_client.certificate_path
        dia.private_key_path = self.ua_client.private_key_path
        if dia.exec_():
            self.ua_client.security_mode = dia.security_mode
            self.ua_client.security_policy = dia.security_policy
            self.ua_client.certificate_path = dia.certificate_path
            self.ua_client.private_key_path = dia.private_key_path

    @pyqtSlot(QItemSelection, QItemSelection, name="show_refs")
    def show_refs(self, selection: QItemSelection, _: QItemSelection) -> None:
        """Show the references for the current node."""
        if not selection.indexes(): # no selection
            return

        node = self.get_current_node()
        if node:
            self._refs_ui.show_refs(node)

    # Todo: This slot is used in different ways, must be splitted.
    def show_attrs(self, selection):
        """Show the attributes for the current node."""
        if isinstance(selection, QItemSelection):
            if not selection.indexes():  # no selection
                return

        node = self.get_current_node()
        if node:
            self._attrs_ui.show_attrs(node)

    @pyqtSlot(Exception, name="show_error")
    def show_error(self, msg: Exception) -> None:
        """Show an error message in the status bar based on an Exception."""
        logger.warning("showing error: %s", msg)
        # Todo: The stylesheet is never changed so it can be set in Qt Designer
        self.ui.statusBar.setStyleSheet(
            "QStatusBar { background-color : red; color : black; }")
        self.ui.statusBar.showMessage(str(msg))
        self.ui.statusBar.show()
        QTimer.singleShot(8000, self.ui.statusBar.hide)

    def get_current_node(self) -> Optional[Node]:
        """Return the Node currently shown in the TreeWidget"""
        return self.tree_ui.get_current_node()

    @pyqtSlot(name="connect")
    def connect(self) -> None:
        """Connect to the server uri entered in the addrComboBox."""
        uri = self.ui.addrComboBox.currentText()
        try:
            self.ua_client.connect(uri)
        except Exception as ex:
            self.show_error(ex)

        self._update_address_list(uri)
        self.tree_ui.set_root_node(self.ua_client.client.nodes.root)
        self.ui.treeView.setFocus()
        # Todo: This doesn't work yet
        # self.load_current_node()

    def _update_address_list(self, uri: str) -> None:
        if uri == self._address_list[0]:
            return
        if uri in self._address_list:
            self._address_list.remove(uri)
        self._address_list.insert(0, uri)
        if len(self._address_list) > self._address_list_max_count:
            self._address_list.pop(-1)

    @pyqtSlot(name="disconnect")
    def disconnect(self) -> None:
        """Disconnect from the server currently connected to."""
        try:
            self.ua_client.disconnect()
        except Exception as ex:
            self.show_error(ex)
            raise
        finally:
            self.save_current_node()
            self.tree_ui.clear()
            self._refs_ui.clear()
            self._attrs_ui.clear()
            self._datachange_ui.clear()
            self._event_ui.clear()

    @pyqtSlot(QCloseEvent, name="closeEvent")
    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle a window close request."""
        self.tree_ui.save_state()
        self._attrs_ui.save_state()
        self._refs_ui.save_state()
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("state", self.saveState())
        self._settings.setValue("address_list", self._address_list)
        self.disconnect()
        super(Window, self).closeEvent(event)

    def save_current_node(self) -> None:
        """Save the current node to be restored after restart."""
        current_node = self.tree_ui.get_current_node()
        if current_node:
            mysettings = self._settings.value("current_node", None)
            if mysettings is None:
                mysettings = {}
            uri = self.ui.addrComboBox.currentText()
            mysettings[uri] = current_node.nodeid.to_string()
            self._settings.setValue("current_node", mysettings)

    def load_current_node(self) -> None:
        """Load the current node from the settings."""
        mysettings = self._settings.value("current_node", None)
        if mysettings is None:
            return
        uri = self.ui.addrComboBox.currentText()
        if uri in mysettings:
            nodeid = ua.NodeId.from_string(mysettings[uri])
            node = self.ua_client.client.get_node(nodeid)
            self.tree_ui.expand_to_node(node)

    def setup_context_menu_tree(self) -> None:
        """Setup the context menu for the TreeView."""
        self.ui.treeView.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.treeView.customContextMenuRequested.connect(
            self.show_context_menu_tree)
        self._context_menu = QMenu()
        self.addAction(self.ui.actionCopyPath)
        self.addAction(self.ui.actionCopyNodeId)
        self._context_menu.addSeparator()
        self._context_menu.addAction(self.ui.actionCall)
        self._context_menu.addSeparator()

    def addAction(self, action: QAction) -> None:
        """Add an action to the Window."""
        self._context_menu.addAction(action)

    @pyqtSlot(name="update_actions_state")
    def update_actions_state(self) -> None:
        """Enable or Disable the actionCall based on the Node class."""
        node = self.get_current_node()
        self.ui.actionCall.setEnabled(False)
        if node and node.get_node_class() == ua.NodeClass.Method:
            self.ui.actionCall.setEnabled(True)

    @pyqtSlot(QPoint, name="show_context_menu_tree")
    def show_context_menu_tree(self, position: QPoint) -> None:
        """Show the context menu at the given position."""
        if self.tree_ui.get_current_node():
            self._context_menu.exec_(
                self.ui.treeView.viewport().mapToGlobal(position))

    @pyqtSlot(name="call_method")
    def call_method(self) -> None:
        """Show the CallMethodDialog."""
        node = self.get_current_node()
        dia = CallMethodDialog(self, self.ua_client.client, node)
        dia.show()


def setup_logging(file_name: str, level: int = logging.ERROR) -> None:
    """Configure logging."""
    fmt_str = "%(asctime)s [%(threadName)-10.10s] [%(levelname)-5.5s] " \
        "[%(filename)25.25s:%(funcName)-25.25s] %(message)s"
    log_formatter = logging.Formatter(fmt_str)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    log_path = "logfiles"
    try:
        os.makedirs(log_path)
    except FileExistsError:
        pass

    file_handler = logging.FileHandler(os.path.join(log_path, file_name))
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)

    logging.info("Free OpcUAClient - logging initialized")
    logging.debug("Set logging to %s", level)


def main() -> None:
    """Main entry point for the app."""
    sys.excepthook = excepthook
    setup_logging("logfile.log", logging.DEBUG)
    app = QApplication(sys.argv)
    client = Window()

    client.show()
    sys.exit(app.exec_())


def excepthook(cls: Exception, exception: str, trace: traceback) -> None:
    """
    Override the system except hook to catch PyQt exceptions.

    :param cls:class of the exception
    :param exception: exception string
    :param trace: traceback of the exception
    :return: None
    """
    logging.critical("Critical error occurred:")
    traceback_text = ""
    for line in traceback.format_tb(trace):
        for line_splitted in line.split("\n"):
            if line_splitted:
                traceback_text = traceback_text + line_splitted + "\n"
                logging.critical(line_splitted)
    logging.critical('%s: %s', cls, exception)
    try:
        QMessageBox.critical(None, "Ein Fehler ist aufgetreten",
                             f"{cls}: {exception}\n {traceback_text}")
    except TypeError:
        pass

if __name__ == "__main__":
    main()
