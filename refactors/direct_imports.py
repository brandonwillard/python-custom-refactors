"""Rewrite indirect references as direct ones.

More specifically, visit each `{pkg}/__init__.py` and gather its package-level
imports and rewrites as follows:

- find `from {pkg}.{sub_pkg} import {mod}` and create the rewrite pair `({pkg}.{mod}, {pkg}.{sub_pkg}.{mod})`
- find `from {pkg}.{mod} import {obj}` and create the rewrite pair `({pkg}.{obj}, {pkg}.{mod}.{obj})`
- find `import {pkg}.{mod} as {mod_ref}` and create the rewrite pair `({pkg}.{mod_ref}, {pkg}.{mod}.{mod_ref})`

After gathering these rewrites, all the project's modules are visited and
searched for these package-level imports (i.e. the first element in each
rewrite pair) and replaced with their direct imports/references (i.e. the
second element in each rewrite pair).

"""
import libcst as cst

from collections import defaultdict
from pathlib import Path


class IndirectImportVisitor(cst.CSTVisitor):
    """Find the source of indirect module/object references within package-level imports.

    Run this on `{pkg}/__init__.py` files to populate a `dict` of potential
    indirect references.  This `dict` can then be used to fix indirect
    references in package modules.

    """

    def __init__(self, pkg_name, rewrites):
        """

        Parameters
        ----------
        pkg_name: str
            Name of the package `__init__.py` being processed
        rewrites: dict
            Storage location for discovered potential indirect references.

        """
        self.pkg_name = pkg_name
        self.rewrites = rewrites

    def visit_Import(self, node):
        # TODO:
        # We don't need to descend into this node
        return False

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if alias.asname:
                name = alias.asname
            else:
                name = alias.name

            indirect_ref = cst.helpers.parse_template_expression(
                self.pkg_name + ".{name}", name=name)

            # TODO: Handle relative imports?
            direct_ref = cst.helpers.parse_template_expression(
                "{mod}.{name}", mod=node.module, name=name)

            indirect_ref_name = cst.helpers.get_full_name_for_node(indirect_ref)

            self.rewrites[indirect_ref_name] = direct_ref
        # We don't need to descend into this node
        return False


class RewriteIndirectImportsTransformer(cst.CSTTransformer):
    """Rewrite uses of indirect imports.

    This will replace imports and attribute accesses using indirect references
    with their direct counterparts.
    """

    def __init__(self, imports_with_indirects, indirect_references):
        """
        Parameters
        ----------
        imports_with_indirects: dict
            A `dict` that maps
        indirect_references: dict
            A `dict` that maps

        """
        self.imports_with_indirects = imports_with_indirects
        self.indirect_references = indirect_references

    def leave_Import(
        self, original_node: cst.Import, updated_node: cst.Import
    ) -> cst.Import:
        # TODO: Replace with direct import.
        # imports_with_indirects
        breakpoint()
        return updated_node  # .with_changes(names=names_to_keep)

    def leave_ImportFrom(
        self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> cst.ImportFrom:
        # TODO: Replace with direct import.
        # imports_with_indirects
        breakpoint()
        return updated_node  # .with_changes(names=names_to_keep)

    def leave_Attribute(self, original_node, updated_node):
        # TODO: Replace with direct reference/attribute access
        breakpoint()
        replacement = self.indirect_references.get(original_node, updated_node)
        return replacement  # .with_changes(names=names_to_keep)


def refine_indirect_references(wrapper, rewrites):
    """Find imports and module references within a module using scope-based considerations.

    Parameters
    ----------
    wrapper :
        The module's metadata wrapper object.
    rewrites : dict
        A `dict` of known package-level imports.

    Returns
    -------
    imports_with_indirects : dict
        Nodes for each import that uses an indirect reference mapped to a node
        using its direct reference.
    indirect_references : dict
        Nodes for each attribute access on an indirect referenc mapped to a
        node using its direct reference.

    """
    scopes = set(wrapper.resolve(cst.metadata.ScopeProvider).values())

    imports_with_indirects = defaultdict(set)
    indirect_references = defaultdict(set)

    # qualified_names = wrapper.resolve(cst.metadata.QualifiedNameProvider)
    parent_nodes = wrapper.resolve(cst.metadata.ParentNodeProvider)

    # ranges = wrapper.resolve(cst.metadata.PositionProvider)
    for scope in scopes:
        for assignment in scope.assignments:
            node = getattr(assignment, "node", None)
            if isinstance(assignment, cst.metadata.Assignment) and isinstance(
                node, (cst.Import, cst.ImportFrom)
            ):
                # Is this import an indirect reference?  If so, prepare it to be replaced.
                if isinstance(node, cst.Import):
                    module_fullnames = [cst.helpers.get_full_name_for_node(m.name) for m in node.names]
                else:
                    module_fullnames = [cst.helpers.get_full_name_for_node(node.module)]

                for mod_name in module_fullnames:
                    replacement_module = rewrites.get(mod_name)

                    if replacement_module:
                        imports_with_indirects[node] = replacement_module

                # TODO: It seems like we should be using FQNs, no?
                # scope.get_qualified_names_for("pkg")

                for ref in assignment.references:
                    ref_parent_node = parent_nodes[ref.node]
                    if isinstance(ref_parent_node, cst.Attribute):
                        ref_fullname = cst.helpers.get_full_name_for_node(ref_parent_node)
                        replacement_module = rewrites.get(ref_fullname)
                        if replacement_module:
                            indirect_references[ref_parent_node] = replacement_module

    return imports_with_indirects, indirect_references



project_path = Path("/tmp/pkg")

rewrites = {}

# 1) Find package-level imports that introduce indirect references
for init in project_path.rglob("__init__.py"):
    pkg_name = init.parts[-2]
    pkg_init_src = init.read_text()
    pkg_init_cst = cst.parse_module(pkg_init_src)

    # TODO: This should be a transformer that also removes the indirect references, no?
    import_visitor = IndirectImportVisitor(pkg_name, rewrites)

    _ = pkg_init_cst.visit(import_visitor)

# 2) Visit each module and replace all the indirect references and imports
for mod_path in project_path.rglob("*.py"):
    if mod_path.stem == "__init__" or any(p.name.startswith(".") for p in mod_path.parents):
        continue
    pkg_name = mod_path.parts[-2]
    mod_name = mod_path.stem
    mod_src = mod_path.read_text()
    mod_cst = cst.parse_module(mod_src)

    wrapper = cst.metadata.MetadataWrapper(mod_cst)
    imports_with_indirects, indirect_references = refine_indirect_references(wrapper, rewrites)

    fixed_module = wrapper.module.visit(RewriteIndirectImportsTransformer(imports_with_indirects, indirect_references))

    # Use difflib to show the changes
    import difflib

    print(
        "".join(
            difflib.unified_diff(mod_src.splitlines(1), fixed_module.code.splitlines(1))
        )
    )

    # if not fixed_module.deep_equals(mod_cst):
    #     pass  # write to file
