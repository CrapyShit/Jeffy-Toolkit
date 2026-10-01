"""Rig / scene validation framework.

Each check finds problems and (when possible) fixes them::

    from jeffy.utils import checks
    for result in checks.run_all():
        print(result)
    checks.get("duplicate_names").fix()

Adding a check is a matter of subclassing :class:`Check` and decorating it
with :func:`register`.
"""

from maya import cmds

from jeffy.controls.control import list_controls
from jeffy.core import attributes, dag, mathlib, naming

ERROR = "error"
WARNING = "warning"
INFO = "info"

_REGISTRY = []


def register(cls):
    _REGISTRY.append(cls)
    return cls


class CheckResult(object):
    def __init__(self, check, issues):
        self.check = check
        self.issues = issues

    @property
    def passed(self):
        return not self.issues

    def __str__(self):
        status = "OK " if self.passed else self.check.severity.upper()
        text = "[%s] %s" % (status, self.check.label)
        if self.issues:
            preview = ", ".join(str(i) for i in self.issues[:5])
            more = " (+%d more)" % (len(self.issues) - 5) if len(self.issues) > 5 else ""
            text += ": %s%s" % (preview, more)
        return text


class Check(object):
    """Base class. Override :meth:`find` (and :meth:`repair` if fixable)."""

    name = "check"
    label = "Check"
    category = "Scene"
    severity = WARNING
    description = ""
    fixable = False

    def find(self):
        return []

    def repair(self, issues):
        raise NotImplementedError

    def run(self):
        return CheckResult(self, self.find())

    def fix(self, issues=None):
        if not self.fixable:
            return False
        issues = self.find() if issues is None else issues
        if issues:
            self.repair(issues)
        return True


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------
@register
class DuplicateNames(Check):
    name = "duplicate_names"
    label = "Duplicate node names"
    severity = ERROR
    description = "Several DAG nodes share the same short name - tools relying on names will fail."
    fixable = True

    def find(self):
        return sorted(naming.find_duplicate_names().keys())

    def repair(self, issues):
        naming.make_names_unique()


@register
class Namespaces(Check):
    name = "namespaces"
    label = "Namespaces in scene"
    description = "Rig files should not contain (non reference) namespaces."
    fixable = True

    def find(self):
        from jeffy.utils import scene

        return scene.list_namespaces()

    def repair(self, issues):
        from jeffy.utils import scene

        scene.remove_namespaces(issues)


@register
class UnknownNodes(Check):
    name = "unknown_nodes"
    label = "Unknown nodes"
    description = "Nodes from plugins that are not available."
    fixable = True

    def find(self):
        return cmds.ls(type=["unknown", "unknownDag", "unknownTransform"]) or []

    def repair(self, issues):
        from jeffy.utils import scene

        scene.delete_unknown_nodes()


@register
class UnknownPlugins(Check):
    name = "unknown_plugins"
    label = "Unknown plugin requirements"
    description = "The scene requires plugins that are not loaded/installed."
    fixable = True

    def find(self):
        return cmds.unknownPlugin(query=True, list=True) or []

    def repair(self, issues):
        from jeffy.utils import scene

        scene.remove_unknown_plugins()


@register
class TurtleNodes(Check):
    name = "turtle_nodes"
    label = "Turtle nodes"
    description = "Leftover Turtle render nodes that force the plugin to load."
    fixable = True

    def find(self):
        from jeffy.utils import scene

        return [n for n in scene.TURTLE_NODES if cmds.objExists(n)]

    def repair(self, issues):
        from jeffy.utils import scene

        scene.delete_turtle_nodes()


@register
class DisplayLayers(Check):
    name = "display_layers"
    label = "Display layers"
    severity = INFO
    description = "Display layers override rig visibility switches."
    fixable = True

    def find(self):
        return [layer for layer in cmds.ls(type="displayLayer") or [] if layer != "defaultLayer"]

    def repair(self, issues):
        from jeffy.utils import scene

        scene.delete_display_layers()


@register
class Expressions(Check):
    name = "expressions"
    label = "Expression nodes"
    severity = INFO
    description = "Expressions are slow and break parallel evaluation - prefer utility nodes."

    def find(self):
        return cmds.ls(type="expression") or []


@register
class SceneUnits(Check):
    name = "scene_units"
    label = "Scene units / up axis"
    severity = INFO
    description = "Expected centimetres and Y up."

    def find(self):
        issues = []
        if cmds.currentUnit(query=True, linear=True) != "cm":
            issues.append("linear unit is %s" % cmds.currentUnit(query=True, linear=True))
        if cmds.upAxis(query=True, axis=True) != "y":
            issues.append("up axis is %s" % cmds.upAxis(query=True, axis=True))
        return issues


@register
class TopLevelNodes(Check):
    name = "top_level_nodes"
    label = "Several top level nodes"
    severity = INFO
    description = "A clean rig file has a single top node."

    def find(self):
        nodes = dag.top_level_nodes()
        return nodes if len(nodes) > 1 else []


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def _mesh_transforms():
    meshes = cmds.ls(type="mesh", noIntermediate=True, long=True) or []
    return sorted(set(cmds.listRelatives(meshes, parent=True, fullPath=True) or []))


@register
class GeometryHistory(Check):
    name = "geometry_history"
    label = "Construction history on geometry"
    category = "Geometry"
    description = "Non deformer history (modelling nodes) left on meshes."
    fixable = True

    def find(self):
        result = []
        for mesh in _mesh_transforms():
            history = cmds.listHistory(mesh, pruneDagObjects=True) or []
            modelling = [h for h in history if not cmds.objectType(h, isAType="geometryFilter")
                         and cmds.nodeType(h) not in ("tweak", "groupId", "groupParts", "objectSet", "dagPose",
                                                      "shadingEngine")
                         and not cmds.objectType(h, isAType="shape")]
            if modelling:
                result.append(mesh)
        return result

    def repair(self, issues):
        for mesh in issues:
            cmds.bakePartialHistory(mesh, prePostDeformers=True)


@register
class UnusedOrigShapes(Check):
    name = "unused_orig_shapes"
    label = "Unused intermediate shapes"
    category = "Geometry"
    fixable = True

    def find(self):
        result = []
        for shape in cmds.ls(type="mesh", intermediateObjects=True, long=True) or []:
            if not cmds.listConnections(shape, source=False, destination=True):
                result.append(shape)
        return result

    def repair(self, issues):
        cmds.delete([s for s in issues if cmds.objExists(s)])


@register
class UnfrozenGeometry(Check):
    name = "unfrozen_geometry"
    label = "Geometry with transforms"
    category = "Geometry"
    severity = INFO
    description = "Meshes whose transforms are not frozen (skinned meshes are skipped)."
    fixable = True

    def find(self):
        from jeffy.deformers import skin

        result = []
        for mesh in _mesh_transforms():
            if skin.find_skin_cluster(mesh):
                continue
            if not mathlib.is_identity(cmds.getAttr(mesh + ".matrix")):
                result.append(mesh)
        return result

    def repair(self, issues):
        for mesh in issues:
            try:
                cmds.makeIdentity(mesh, apply=True, translate=True, rotate=True, scale=True)
            except RuntimeError:
                continue


@register
class ShapeNames(Check):
    name = "shape_names"
    label = "Shape names do not match transforms"
    category = "Geometry"
    severity = INFO
    fixable = True

    def find(self):
        result = []
        for shape in cmds.ls(shapes=True, noIntermediate=True, long=True) or []:
            if cmds.nodeType(shape) == "camera" or cmds.referenceQuery(shape, isNodeReferenced=True):
                continue
            parent = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
            if not naming.short_name(shape).startswith(naming.short_name(parent) + "Shape"):
                result.append(shape)
        return result

    def repair(self, issues):
        parents = set(cmds.listRelatives(issues, parent=True, fullPath=True) or [])
        naming.fix_shape_names(list(parents))


@register
class NegativeScale(Check):
    name = "negative_scale"
    label = "Negative scale"
    category = "Geometry"
    description = "Negatively scaled transforms flip normals and break mirroring."

    def find(self):
        return [n for n in cmds.ls(type="transform", long=True) or []
                if any(v < 0 for v in cmds.getAttr(n + ".scale")[0])]


# ---------------------------------------------------------------------------
# Rig
# ---------------------------------------------------------------------------
@register
class ControlsNotZeroed(Check):
    name = "controls_not_zeroed"
    label = "Controls not at default values"
    category = "Rig"
    description = "Controls should rest at their default values (use offset groups)."
    fixable = True

    def find(self):
        result = []
        for control in list_controls():
            for attr in cmds.listAttr(control, keyable=True, unlocked=True, scalar=True) or []:
                default = attributes.get_default(control, attr)
                value = cmds.getAttr("%s.%s" % (control, attr))
                if isinstance(default, (int, float)) and isinstance(value, (int, float)) and abs(
                        value - default) > 1e-4:
                    result.append(control)
                    break
        return result

    def repair(self, issues):
        attributes.reset(issues)


@register
class KeyedControls(Check):
    name = "keyed_controls"
    label = "Animation keys on controls"
    category = "Rig"
    description = "Rig files should not contain animation."
    fixable = True

    def find(self):
        result = []
        for control in list_controls():
            curves = cmds.listConnections(control, type="animCurve", source=True, destination=False) or []
            if any(cmds.nodeType(c) in ("animCurveTL", "animCurveTA", "animCurveTU", "animCurveTT")
                   for c in curves):
                result.append(control)
        return result

    def repair(self, issues):
        for control in issues:
            cmds.cutKey(control, clear=True)


@register
class MissingControllerTags(Check):
    name = "missing_controller_tags"
    label = "Controls without controller tag"
    category = "Rig"
    severity = INFO
    description = "Controller tags improve parallel evaluation and pick walking."
    fixable = True

    def find(self):
        return [c for c in list_controls() if not cmds.controller(c, query=True, isController=True)]

    def repair(self, issues):
        for control in issues:
            cmds.controller(control)


@register
class JointRotations(Check):
    name = "joint_rotations"
    label = "Joints with rotate values"
    category = "Rig"
    description = "Bind joints should keep their orientation in jointOrient, not rotate."
    fixable = True

    def find(self):
        result = []
        for joint in cmds.ls(type="joint", long=True) or []:
            plug = joint + ".rotate"
            if cmds.listConnections(plug, source=True, destination=False) or any(
                    cmds.listConnections(plug + axis, source=True, destination=False) for axis in "XYZ"):
                continue
            if any(abs(v) > 1e-3 for v in cmds.getAttr(plug)[0]):
                result.append(joint)
        return result

    def repair(self, issues):
        from jeffy.joints import orient

        orient.freeze_rotations(issues)


@register
class JointScale(Check):
    name = "joint_scale"
    label = "Joints with non uniform / non 1 scale"
    category = "Rig"

    def find(self):
        result = []
        for joint in cmds.ls(type="joint", long=True) or []:
            if cmds.listConnections(joint + ".scale", source=True, destination=False):
                continue
            if any(abs(v - 1.0) > 1e-3 for v in cmds.getAttr(joint + ".scale")[0]):
                result.append(joint)
        return result


@register
class VisibleIkHandles(Check):
    name = "visible_ik_handles"
    label = "Visible IK handles"
    category = "Rig"
    severity = INFO
    fixable = True

    def find(self):
        return [h for h in cmds.ls(type="ikHandle") or []
                if cmds.getAttr(h + ".visibility") and not cmds.getAttr(h + ".visibility", lock=True)]

    def repair(self, issues):
        for handle in issues:
            cmds.setAttr(handle + ".visibility", 0)


@register
class SkinMaxInfluences(Check):
    name = "skin_max_influences"
    label = "Vertices over the max influence count"
    category = "Deformation"
    description = "Game engines usually support 4 or 8 influences per vertex."
    fixable = True

    def find(self):
        from jeffy.deformers import skin, weights

        result = []
        for skin_cluster in cmds.ls(type="skinCluster") or []:
            try:
                flat, influences, _count = skin.get_weights(skin_cluster)
            except (ValueError, RuntimeError):
                continue
            limit = cmds.getAttr(skin_cluster + ".maxInfluences")
            if weights.vertices_over_limit(flat, len(influences), limit):
                result.append(skin_cluster)
        return result

    def repair(self, issues):
        from jeffy.deformers import skin

        for skin_cluster in issues:
            geometry = cmds.skinCluster(skin_cluster, query=True, geometry=True)[0]
            skin.limit_influences(cmds.listRelatives(geometry, parent=True)[0],
                                  cmds.getAttr(skin_cluster + ".maxInfluences"), undoable=False)


@register
class ExtraBindPoses(Check):
    name = "extra_bind_poses"
    label = "Unused bind poses"
    category = "Deformation"
    severity = INFO
    fixable = True

    def find(self):
        return [p for p in cmds.ls(type="dagPose") or []
                if not cmds.listConnections(p + ".message", source=False, destination=True)]

    def repair(self, issues):
        cmds.delete([p for p in issues if cmds.objExists(p)])


@register
class EmptyGroups(Check):
    name = "empty_groups"
    label = "Empty groups"
    category = "Scene"
    severity = INFO
    fixable = True

    def find(self):
        from jeffy.utils import scene

        return scene.find_empty_groups()

    def repair(self, issues):
        from jeffy.utils import scene

        scene.delete_empty_groups()


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------
def all_checks():
    return [cls() for cls in _REGISTRY]


def get(name):
    for cls in _REGISTRY:
        if cls.name == name:
            return cls()
    raise KeyError(name)


def run_all(categories=None):
    results = []
    for check in all_checks():
        if categories and check.category not in categories:
            continue
        try:
            results.append(check.run())
        except Exception as error:  # a broken check must not stop the others
            results.append(CheckResult(check, ["check failed: %s" % error]))
    return results


def fix_all(results=None):
    results = results or run_all()
    fixed = []
    for result in results:
        if not result.passed and result.check.fixable:
            result.check.fix(result.issues)
            fixed.append(result.check.name)
    return fixed


def report(results=None):
    results = results or run_all()
    lines = [str(r) for r in results]
    failed = sum(1 for r in results if not r.passed)
    lines.append("%d / %d checks passed" % (len(results) - failed, len(results)))
    return "\n".join(lines)
