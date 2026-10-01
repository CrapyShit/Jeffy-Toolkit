"""Proxy (low cost) geometry for fast animation playback.

* :func:`proxies_from_skin` - cut a skinned mesh into one rigid piece per
  influence (each face goes to the influence with the most weight).
* :func:`capsule_proxies` - simple cylinders along joint chains.
"""

from maya import cmds

from jeffy.core import mathlib, naming, transform
from jeffy.geometry import mesh as mesh_tools


def face_influence_map(flat, influence_count, face_vertices):
    """Pure helper: index of the dominant influence of every face."""
    result = []
    for vertices in face_vertices:
        totals = [0.0] * influence_count
        for v in vertices:
            row = flat[v * influence_count:(v + 1) * influence_count]
            for i, w in enumerate(row):
                totals[i] += w
        result.append(max(range(influence_count), key=lambda i: totals[i]))
    return result


def proxies_from_skin(meshes, suffix="_PRX", group_name="proxy_GRP", attach="constraint"):
    """Create rigid proxy pieces from skinned meshes.

    :param attach: ``constraint`` (parent + scale constraints), ``parent``
        (parented under the joints) or ``none``
    :returns: list of created proxy meshes
    """
    from jeffy.deformers import skin

    if isinstance(meshes, str):
        meshes = [meshes]
    group = group_name if cmds.objExists(group_name) else cmds.createNode("transform", name=group_name,
                                                                           skipSelect=True)
    created = []
    for mesh in meshes:
        skin_cluster = skin.require_skin(mesh)
        flat, influences, _count = skin.get_weights(skin_cluster)
        faces = mesh_tools.get_face_vertices(mesh)
        owners = face_influence_map(flat, len(influences), faces)
        by_influence = {}
        for face, owner in enumerate(owners):
            by_influence.setdefault(owner, []).append(face)
        all_faces = set(range(len(faces)))
        for owner, face_ids in sorted(by_influence.items()):
            influence = influences[owner]
            name = "%s_%s%s" % (naming.strip_namespace(mesh), naming.strip_namespace(influence), suffix)
            piece = mesh_tools.duplicate_clean(mesh, name=name)
            delete = sorted(all_faces.difference(face_ids))
            if delete:
                cmds.delete(mesh_tools.component_list(piece, delete, "f"))
            cmds.delete(piece, constructionHistory=True)
            if attach == "parent":
                piece = cmds.parent(piece, influence)[0]
            else:
                piece = cmds.parent(piece, group)[0]
                if attach == "constraint":
                    cmds.parentConstraint(influence, piece, maintainOffset=True)
                    cmds.scaleConstraint(influence, piece, maintainOffset=True)
            created.append(piece)
    return created


def capsule_proxies(joints, radius_ratio=0.15, suffix="_PRX", group_name="proxy_GRP"):
    """A cylinder from each joint to its first child joint."""
    group = group_name if cmds.objExists(group_name) else cmds.createNode("transform", name=group_name,
                                                                           skipSelect=True)
    created = []
    for joint in joints:
        children = cmds.listRelatives(joint, children=True, type="joint") or []
        if not children:
            continue
        start = transform.get_position(joint)
        end = transform.get_position(children[0])
        length = mathlib.distance(start, end)
        if length < 1e-4:
            continue
        name = naming.unique_name(naming.strip_namespace(joint) + suffix)
        cylinder = cmds.polyCylinder(name=name, radius=length * radius_ratio, height=length, axis=(1, 0, 0),
                                     subdivisionsX=8, subdivisionsY=1, constructionHistory=False)[0]
        cmds.xform(cylinder, worldSpace=True, translation=mathlib.midpoint(start, end))
        cmds.delete(cmds.aimConstraint(children[0], cylinder, aimVector=(1, 0, 0), worldUpType="objectrotation",
                                       worldUpObject=joint, upVector=(0, 1, 0), worldUpVector=(0, 1, 0)))
        cylinder = cmds.parent(cylinder, group)[0]
        cmds.parentConstraint(joint, cylinder, maintainOffset=True)
        created.append(cylinder)
    return created
