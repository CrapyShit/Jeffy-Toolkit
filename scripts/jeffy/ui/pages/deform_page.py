"""Deform tab: skinning, blendshapes and deformers."""

from jeffy.core import settings
from jeffy.ui import actions
from jeffy.ui import widgets as w


class DeformPage(w.Page):
    TITLE = "Deform"

    def build(self):
        bind = self.section("Skin - Bind / IO")
        self.max_inf = w.spin(settings.get("skin_max_influences", 4), 1, 32, 0, 1)
        self.bind_method = w.combo(["closest", "hierarchy", "heatmap", "geodesic"], "closest")
        bind.add(w.row(("Max infl.", self.max_inf), ("Method", self.bind_method),
                       w.button("Bind Skin", lambda: actions.bind_skin(self.max_inf.value(),
                                                                       self.bind_method.currentText()),
                                "Select joints and meshes")))
        self.import_method = w.combo(["auto", "index", "position"], "auto",
                                     "auto: by vertex index when the vertex count matches, else by position")
        bind.add(w.row(w.button("Export Weights...", actions.export_skin_weights),
                       ("Import by", self.import_method),
                       w.button("Import Weights...", lambda: actions.import_skin_weights(
                           self.import_method.currentText()))))
        bind.add(w.grid([
            w.button("Copy Skin", actions.copy_skin, "Source mesh first, then targets"),
            w.button("Mirror Skin +X > -X", lambda: actions.mirror_skin("x", True)),
            w.button("Mirror Skin -X > +X", lambda: actions.mirror_skin("x", False)),
            w.button("Unbind", lambda: actions.unbind_skin(False)),
            w.button("Combine Skinned", actions.combine_skinned),
            w.button("Skin Info", actions.skin_info),
        ], 3))

        clean = self.section("Skin - Cleanup")
        self.prune = w.spin(settings.get("skin_prune_threshold", 0.01), 0.0001, 0.5, 4, 0.005)
        clean.add(w.row(("Threshold", self.prune),
                        w.button("Prune Weights", lambda: actions.prune_weights(self.prune.value()))))
        clean.add(w.row(("Max infl.", w.label("uses the value above")),
                        w.button("Limit Influences", lambda: actions.limit_influences(self.max_inf.value()))))
        clean.add(w.grid([
            w.button("Remove Unused Infl.", actions.remove_unused_influences),
            w.button("Rebind At Current Pose", actions.rebind_at_current_pose,
                     "Reset bindPreMatrix after moving joints (weights kept)"),
            w.button("Go To Bind Pose", actions.go_to_bind_pose),
            w.button("Select Influences", actions.select_influences),
            w.button("Select Influenced Verts", actions.select_influenced_vertices),
            w.button("Dual Quaternion", lambda: actions.set_skinning_method("dual_quaternion")),
            w.button("Linear", lambda: actions.set_skinning_method("linear")),
            w.button("Weight Blended", lambda: actions.set_skinning_method("blended")),
        ], 3))

        vertex = self.section("Skin - Vertices")
        vertex.add(w.grid([
            w.button("Copy Vtx Weights", actions.copy_vertex_weights),
            w.button("Paste Vtx Weights", actions.paste_vertex_weights),
            w.button("Average Weights", actions.average_vertex_weights),
            w.button("Move Weights", actions.move_weights, "Select source joint, target joint, then the mesh or "
                                                           "vertices"),
        ], 2))
        self.iterations = w.spin(2, 1, 100, 0, 1)
        self.strength = w.spin(0.5, 0.01, 1.0, 2, 0.05)
        vertex.add(w.row(("Iterations", self.iterations), ("Strength", self.strength),
                         w.button("Smooth Weights", lambda: actions.smooth_weights(self.iterations.value(),
                                                                                   self.strength.value()))))

        bs = self.section("Blendshapes", expanded=False)
        self.falloff = w.spin(2.0, 0.0, 1000.0, 2, 0.5, "Split falloff width")
        bs.add(w.grid([
            w.button("Add Targets", actions.add_blendshape_targets, "Targets first, base mesh last"),
            w.button("Extract Targets", actions.extract_blendshape_targets),
            w.button("Mirror Target", actions.mirror_blendshape_target, "Base first, then targets"),
            w.button("Symmetrize +X > -X", lambda: actions.symmetrize_blendshape_target("x", True),
                     "Base first, then targets"),
            w.button("Transfer Blendshapes", actions.transfer_blendshapes, "Source base, then target mesh"),
        ], 3))
        bs.add(w.row(("Falloff", self.falloff), w.button("Split Target L/R", lambda: actions.split_blendshape_target(
            self.falloff.value()), "Base first, then targets")))

        deformers = self.section("Deformers / Proxies", expanded=False)
        deformers.add(w.grid([
            w.button("Soft Selection Cluster", actions.soft_selection_cluster),
            w.button("Wrap", actions.create_wrap, "Driven meshes first, driver last"),
            w.button("Delta Mush", actions.create_delta_mush),
            w.button("Toggle Deformers", actions.toggle_deformers),
            w.button("Mirror Deformer Weights", actions.mirror_deformer_weights, "Select the deformer"),
            w.button("Export Deformer Weights", actions.export_deformer_weights),
            w.button("Import Deformer Weights", actions.import_deformer_weights),
            w.button("Proxies From Skin", actions.proxies_from_skin, "Rigid pieces per influence"),
        ], 2))
