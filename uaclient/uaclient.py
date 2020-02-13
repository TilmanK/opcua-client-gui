"""UaClient definition for usage in GUI application."""
import logging
from typing import Optional, Dict, List

from PyQt5.QtCore import QSettings

from asyncua.sync import ua, Subscription
from asyncua.sync import Client
from asyncua.sync import Node
from asyncua import crypto
from asyncua.tools import endpoint_to_strings
from asyncua.ua import NodeId, EndpointDescription

from uaclient.handler import DataChangeHandler, EventHandler


class UaClient:
    """
    OPC-Ua client specialized for the need of GUI client
    return exactly what GUI needs, no customization possible
    """

    def __init__(self) -> None:
        """Create a new UaClient."""

        # opcua high level client for communication with the server
        self.client: Optional[Client] = None

        # stores the current connection state
        self._connected: bool = False

        # Todo: Check if we really need two Subscriptions
        # holds the Subscription for data changes if connected
        self._datachange_sub: Optional[Subscription] = None

        # holds the Subscription for events if connected
        self._event_sub: Optional[Subscription] = None

        # holds all the datachange subscriptions
        self._subs_dc: Dict[NodeId, int] = {}

        # holds all the event subscriptions
        self._subs_ev: Dict[NodeId, int] = {}

        self.security_mode: Optional[str] = None
        self.security_policy: Optional[str] = None
        self.certificate_path: Optional[str] = None
        self.private_key_path: Optional[str] = None

    def _reset(self) -> None:
        """Reset the UaClient"""
        self.client = None
        self._connected = False
        self._datachange_sub = None
        self._event_sub = None
        self._subs_dc.clear()
        self._subs_ev.clear()

    @staticmethod
    def get_endpoints(uri: str) -> List[EndpointDescription]:
        """Get and return the EndpointDescriptions for the given uri."""
        client = Client(uri, timeout=2)
        # client.connect_and_get_server_endpoints()
        endpoints: List[EndpointDescription]\
            = client.connect_and_get_server_endpoints()
        for endpoint in endpoints:
            logging.debug("Got endpoint: %s", endpoint_to_strings(endpoint))
        return endpoints

    def load_security_settings(self, uri: str) -> None:
        """Load and set the security settings from QSettings"""
        settings = QSettings().value("security_settings", None)
        try:
            if uri in settings:
                mode, policy, cert, key = settings[uri]
                self.security_mode = mode
                self.security_policy = policy
                self.certificate_path = cert
                self.private_key_path = key
        except TypeError:
            logging.info("No security settings are stored.")

    def save_security_settings(self, uri: str) -> None:
        """Store the security settings into QSettings."""
        settings = QSettings().value("security_settings", None)
        if settings is None:
            settings = {}
        settings[uri] = [self.security_mode, self.security_policy,
                         self.certificate_path, self.private_key_path]
        logging.debug("Storing security settings for uri: %s", uri)
        logging.debug("%s", settings)
        QSettings().setValue("security_settings", settings)

    def get_node(self, nodeid: NodeId) -> Node:
        """Get a Node by its NodeId."""
        # client must be available when called
        assert self.client
        return self.client.get_node(nodeid)

    def connect(self, uri: str) -> None:
        """Connect to the given URI."""
        self.disconnect()
        logging.info("Connecting to %s with parameters", uri)
        logging.debug("Security:  %s, %s, %s, %s",
                      self.security_mode, self.security_policy,
                      self.certificate_path, self.private_key_path)
        self.client = Client(uri)
        if self.security_mode is not None and self.security_policy is not None:
            # Todo: Refactor this
            self.client.set_security(
                getattr(crypto.security_policies, 'SecurityPolicy' +
                        self.security_policy),
                self.certificate_path,
                self.private_key_path,
                mode=getattr(ua.MessageSecurityMode, self.security_mode)
            )
        self.client.connect()
        self._connected = True
        self.save_security_settings(uri)

    def disconnect(self) -> None:
        """Disconnect from the server."""
        if self._connected:
            print("Disconnecting from server")
            try:
                # client must be available
                assert self.client
                self.client.disconnect()
            finally:
                self._reset()

    def subscribe_datachange(self, node: Node, handler: DataChangeHandler)\
            -> int:
        """Subscribe to a datachange."""
        assert self.client
        if not self._datachange_sub:
            self._datachange_sub = \
                self.client.create_subscription(500, handler)
        handle: int = self._datachange_sub.subscribe_data_change(node)
        self._subs_dc[node.nodeid] = handle
        return handle

    def unsubscribe_datachange(self, node: Node) -> None:
        """Unsubscribe from a datachange."""
        assert self._datachange_sub
        self._datachange_sub.unsubscribe(self._subs_dc[node.nodeid])

    def subscribe_events(self, node: Node, handler: EventHandler) -> int:
        """Subscribe to an event."""
        assert self.client
        if not self._event_sub:
            self._event_sub = self.client.create_subscription(500, handler)
        handle: int = self._event_sub.subscribe_events(node)
        self._subs_ev[node.nodeid] = handle
        return handle

    def unsubscribe_events(self, node: Node) -> None:
        """Unsubscribe from an event."""
        assert self._event_sub
        self._event_sub.unsubscribe(self._subs_ev[node.nodeid])
