"""Attributes tab: add/lock/proxy/reorder attributes, connections and SDKs."""

from jeffy.ui import actions
from jeffy.ui import widgets as w

LOCK_ATTRS = [["tx", "ty", "tz"], ["rx", "ry", "rz"], ["sx", "sy", "sz"], ["v"]]


class AttributesPage(w.Page):
    TITLE = "Attributes"

    def build(self):
        add = self.section("Add Attribute")
        self.attr_name = w.line_edit("", "attribute name")
        self.attr_type = w.combo(["float", "int", "bool", "enum", "string", "angle", "distance", "vector", "message"],
                                 "float")
        add.add(w.row(("Name", self.attr_name), ("Type", self.attr_type)))
        self.minimum = w.line_edit("", "min")
        self.maximum = w.line_edit("", "max")
        self.default = w.line_edit("", "default")
        add.add(w.row(("Min", self.minimum), ("Max", self.maximum), ("Default", self.default)))
        self.enum_names = w.line_edit("off:on", "enum names a:b:c")
        self.keyable = w.check("Keyable", True)
        add.add(w.row(("Enum", self.enum_names), self.keyable))
        add.add(w.button("Add To Selected", self._add_attr))
        self.separator = w.line_edit("settings")
        add.add(w.row(("Separator", self.separator),
                      w.button("Add Separator", lambda: actions.add_separator(self.separator.text() or "settings"))))

        lock = self.section("Lock / Hide")
        self.lock_boxes = {}
        rows = []
        for group in LOCK_ATTRS:
            boxes = []
            for attr in group:
                box = w.check(attr, attr != "v")
                self.lock_boxes[attr] = box
                boxes.append(box)
            rows.append(w.row(*boxes, stretch=True))
        for widget in rows:
            lock.add(widget)
        lock.add(w.grid([
            w.button("Lock + Hide", lambda: actions.lock_hide(self._lock_attrs(), True, True)),
            w.button("Lock", lambda: actions.lock_hide(self._lock_attrs(), True, False)),
            w.button("Unlock + Show", lambda: actions.unlock_show(self._lock_attrs())),
        ], 3))

        manage = self.section("Manage", expanded=False)
        manage.add(w.grid([
            w.button("Move Up", lambda: actions.move_attribute(-1), "Channel box selected user attributes"),
            w.button("Move Down", lambda: actions.move_attribute(1)),
            w.button("Reset To Defaults", actions.reset_attributes),
            w.button("Proxy Attribute", actions.add_proxy_attribute,
                     "Channel box attr of the first selected becomes a proxy on the others"),
            w.button("Copy User Attrs", lambda: actions.copy_attributes(False, False), "First -> others"),
            w.button("Copy + Connect", lambda: actions.copy_attributes(True, False),
                     "New attributes are driven by the source"),
            w.button("Transfer (move)", lambda: actions.copy_attributes(False, True),
                     "Move attributes and their connections to the other node"),
        ], 3))

        connect = self.section("Connections", expanded=False)
        self.connect_t = w.check("translate", True)
        self.connect_r = w.check("rotate", True)
        self.connect_s = w.check("scale", False)
        connect.add(w.row(self.connect_t, self.connect_r, self.connect_s,
                          w.button("Connect First > Rest", self._connect)))
        connect.add(w.grid([
            w.button("Connect CB Attrs", actions.connect_channel_box_attributes,
                     "Channel box selected attrs of the first -> same attrs on the rest"),
            w.button("Break Connections", actions.break_connections),
            w.button("Transfer Connections", actions.transfer_connections, "First node's connections -> second"),
        ], 3))

        sdk = self.section("Set Driven Keys", expanded=False)
        sdk.add(w.grid([
            w.button("Copy SDK", actions.copy_driven_keys, "Source first, then targets"),
            w.button("Mirror SDK", actions.mirror_driven_keys, "Copies to L_/R_ counterparts"),
            w.button("Export SDK...", actions.export_driven_keys),
            w.button("Import SDK...", actions.import_driven_keys),
        ], 2))

    def _lock_attrs(self):
        return [attr for attr, box in self.lock_boxes.items() if box.isChecked()]

    def _connect(self):
        attrs = [name for name, box in (("translate", self.connect_t), ("rotate", self.connect_r),
                                        ("scale", self.connect_s)) if box.isChecked()]
        actions.connect_attributes(attrs)

    @staticmethod
    def _number(text):
        text = text.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _add_attr(self):
        attr_type = self.attr_type.currentText()
        default = self._number(self.default.text())
        if attr_type in ("int", "bool", "enum") and default is not None:
            default = int(default)
        if attr_type == "string":
            default = self.default.text() or None
        actions.add_attribute(self.attr_name.text().strip(), attr_type, default=default,
                              minimum=self._number(self.minimum.text()),
                              maximum=self._number(self.maximum.text()),
                              enum_names=self.enum_names.text() or None, keyable=self.keyable.isChecked())
