"""Hand component: finger chains with FK controls and pose attributes."""

from jeffy.autorig import components
from jeffy.autorig.components.base import Component
from jeffy.controls.control import Control
from jeffy.core import mathlib
from jeffy.rig import fingers

#: Default left hand finger guides (wrist at about (67, 145, -2)).
FINGER_GUIDES = {
    "thumb": [(69.0, 143.0, 3.0), (72.0, 141.0, 6.0), (75.0, 140.0, 8.0), (78.0, 139.0, 9.0)],
    "index": [(70.0, 145.0, 1.5), (76.0, 145.0, 2.5), (80.0, 145.0, 2.5), (83.0, 145.0, 2.5), (85.5, 145.0, 2.5)],
    "middle": [(70.0, 145.5, -1.0), (77.0, 145.5, -0.5), (81.5, 145.5, -0.5), (85.0, 145.5, -0.5),
               (87.5, 145.5, -0.5)],
    "ring": [(70.0, 145.0, -3.5), (76.5, 145.0, -3.0), (80.5, 145.0, -3.0), (83.5, 145.0, -3.0), (86.0, 145.0, -3.0)],
    "pinky": [(69.5, 144.5, -5.5), (75.0, 144.5, -5.5), (78.0, 144.5, -5.5), (80.5, 144.5, -5.5),
              (82.5, 144.5, -5.5)],
}


def _finger_list(settings):
    value = (settings or {}).get("fingers", HandComponent.SETTINGS["fingers"])
    return [f.strip() for f in str(value).split(",") if f.strip()]


@components.register
class HandComponent(Component):
    TYPE = "hand"
    DESCRIPTION = "Fingers with FK controls and fist / spread / relax / curl attributes."
    DEFAULT_NAME = "hand"
    DEFAULT_SIDE = "L"
    MIRRORABLE = True
    SETTINGS = {"fingers": "thumb,index,middle,ring,pinky", "metacarpals": True}

    @classmethod
    def guide_definitions(cls, settings=None):
        definitions = []
        for n, finger in enumerate(_finger_list(settings)):
            points = FINGER_GUIDES.get(finger)
            if points is None:  # unknown finger name: offset copy of the middle finger
                points = [mathlib.add(p, (0.0, 0.0, -2.5 * n)) for p in FINGER_GUIDES["middle"]]
            parent = None
            for i, point in enumerate(points):
                label = "%s%02d" % (finger, i + 1)
                definitions.append((label, point, parent))
                parent = label
        return definitions

    def _chains(self):
        chains = []
        for finger in _finger_list(self.settings):
            labels = [d[0] for d in self.guide_definitions(self.settings) if d[0].startswith(finger)
                      and d[0][len(finger):].isdigit()]
            chains.append((finger, labels))
        return chains

    def build_skeleton(self, parent):
        self.finger_joints = []
        self.bind_joints = []
        for finger, labels in self._chains():
            positions = [self.position(label) for label in labels]
            joints = self.create_chain(labels, positions, parent=parent, up_mode="world",
                                       world_up=(0.0, 1.0, 0.0))
            self.finger_joints.append((finger, joints))
            self.bind_joints.extend(joints[:-1])

    def build_rig(self):
        if not self.finger_joints:
            return
        all_points = [self.position(d[0]) for d in self.guide_definitions(self.settings)]
        center = mathlib.centroid(all_points)
        mins, maxs = mathlib.bounding_box(all_points)
        span = max(maxs[i] - mins[i] for i in range(3))
        holder = Control.create(self.name + "Fingers", side=self.side, shape="hand", size=span * 0.25, axis="y",
                                parent=self.controls_group, position=mathlib.add(center, (0.0, span * 0.35, 0.0)),
                                lock=("t", "r", "s", "v"), secondary=True)
        base_index = {}
        if self.setting("metacarpals"):
            base_index = {finger: 1 for finger, joints in self.finger_joints
                          if "thumb" not in finger and len(joints) > 4}
        result = fingers.build_fingers(self.finger_joints, side=self.side, attr_holder=holder.node,
                                       control_parent=self.controls_group, size=span * 0.06,
                                       curl_axis="z", spread_axis="y", base_index=base_index)
        controls = [holder]
        for ctls in result["controls"].values():
            controls.extend(ctls)
        self.register_controls(controls)
        self.add_output("fingers", holder.node, None)
