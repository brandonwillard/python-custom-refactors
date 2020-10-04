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
import os
import importlib
import pkgutil

import libcst as cst

from dataclasses import dataclass, field
from collections import defaultdict, OrderedDict
from pathlib import Path
from typing import Union

from setuptools import find_packages


@dataclass
class PythonPackageInfo:
    """An object that computes information about a package's sub-packages and modules."""

    filenames_to_modules: OrderedDict = field(repr=False)
    fullnames_to_modules: OrderedDict = field(repr=False)
    fullnames_to_packages: OrderedDict = field(repr=False)
    packages_to_modules: OrderedDict = field(repr=False)
    paths_to_packages: OrderedDict = field(repr=False)
    packages_to_paths: OrderedDict

    def __init__(self, pkg_dir):
        pkg_dir = Path(pkg_dir)
        packages = find_packages(where=pkg_dir.parent.as_posix())
        package_infos = [
            (p, (pkg_dir.parent / p.replace(".", os.path.sep)).as_posix())
            for p in packages
        ]

        # Get the `__init__.py`
        # first_mod = next(pkgutil.iter_modules(["/tmp/pkg"]))
        # root_init_mod = first_mod.module_finder.find_module("__init__")

        self.fullnames_to_modules = OrderedDict()
        self.filenames_to_modules = OrderedDict()
        self.packages_to_modules = OrderedDict()
        self.packages_to_paths = OrderedDict()
        self.paths_to_packages = OrderedDict()
        self.fullnames_to_packages = OrderedDict()

        for package_name, package_path in package_infos:
            self.packages_to_paths[package_name] = Path(package_path)
            self.paths_to_packages[Path(package_path)] = package_name

            pkg_modinfos = []
            for old_modinfo in pkgutil.iter_modules([package_path]):
                mod_fullname = f"{package_name}.{old_modinfo.name}"
                mod_filename = Path(
                    old_modinfo.module_finder.find_module(
                        old_modinfo.name
                    ).get_filename()
                )

                # This `ModuleInfo` uses the module's full name
                new_modinfo = pkgutil.ModuleInfo(
                    old_modinfo.module_finder, mod_fullname, old_modinfo.ispkg
                )
                pkg_modinfos.append(new_modinfo)

                self.filenames_to_modules[mod_filename] = new_modinfo
                self.fullnames_to_modules[mod_fullname] = new_modinfo
                self.fullnames_to_packages[mod_fullname] = package_name

            self.packages_to_modules[package_name] = pkg_modinfos


class IndirectImportTransformer(cst.CSTTransformer):
    """Find the source of indirect module/object references within package-level imports.

    Run this on `{pkg}/__init__.py` files to populate a `dict` of potential
    indirect references.  This `dict` can then be used to fix indirect
    references in package modules.

    """

    def __init__(self, pkg_info, pkg_dir, rewrites):
        """Create an `IndirectImportTransformer` instance.

        Parameters
        ----------
        pkg_info: PythonPackageInfo
            The package information
        pkg_dir: str or `Path`
            Path of the (sub-)package for which `__init__.py` is to be processed.
        rewrites: dict
            Storage location for discovered potential indirect references.

        """
        self.pkg_info = pkg_info
        self.pkg_dir = Path(pkg_dir)
        self.pkg_fullname = self.pkg_info.paths_to_packages[self.pkg_dir]
        self.rewrites = rewrites

    def leave_Import(
        self, original_node: cst.Import, updated_node: cst.Import
    ) -> Union[cst.Import, cst.RemovalSentinel]:

        name_idxs_to_remove = []

        for n, alias in enumerate(original_node.names):

            if alias.asname:
                # If an `import ...` has an alias, then it simply needs to be
                # replaced, because that alias will necessarily serve as a type
                # of indirect import.

                indirect_ref = cst.helpers.parse_template_expression(
                    self.pkg_fullname + ".{name}", name=alias.asname.name
                )

                direct_ref = alias.name
                indirect_ref_name = cst.helpers.get_full_name_for_node(indirect_ref)

                self.rewrites[indirect_ref_name] = direct_ref

                name_idxs_to_remove.append(n)
            else:
                module_fullname = cst.helpers.get_full_name_for_node(alias.name)
                module_package = self.pkg_info.fullnames_to_packages[module_fullname]

                if module_package == self.pkg_fullname:
                    pass
                elif module_package >= self.pkg_fullname:
                    # The imported object is in a sub-package of this package
                    # We could remove it, but that would require new `import`
                    # statements in the modules that use this direct reference.

                    # TODO: This seems like a good optional functionality to
                    # offer.
                    pass
                else:
                    # This import is for an object above this package level,
                    # but it's not an aliased import, so it can't be an
                    # indirect reference, but it could definitely be
                    # introducing some unwanted (sub-)package dependencies.
                    pass

        if name_idxs_to_remove:
            new_names = tuple(
                name
                for n, name in enumerate(updated_node.names)
                if n not in name_idxs_to_remove
            )

            if not new_names:
                return cst.RemoveFromParent()

            updated_node = updated_node.with_changes(names=new_names)

        return updated_node

    def leave_ImportFrom(
        self, original_node: cst.Import, updated_node: cst.Import
    ) -> Union[cst.Import, cst.RemovalSentinel]:

        # TODO: Handle star imports?

        if original_node.module:
            mod_name = original_node.module
        elif original_node.relative:
            mod_name = cst.Name(
                importlib.util.resolve_name(
                    "." * len(original_node.relative), self.pkg_fullname
                )
            )

        for alias in original_node.names:

            indirect_name = alias.asname.name if alias.asname else alias.name
            direct_name = alias.name

            indirect_ref = cst.helpers.parse_template_expression(
                self.pkg_fullname + ".{name}", name=indirect_name
            )

            direct_ref = cst.helpers.parse_template_expression(
                "{mod}.{name}", mod=mod_name, name=direct_name
            )

            indirect_ref_name = cst.helpers.get_full_name_for_node(indirect_ref)

            if direct_ref.deep_equals(indirect_ref):
                continue

            self.rewrites[indirect_ref_name] = direct_ref

        return cst.RemoveFromParent()


class RewriteIndirectImportsTransformer(cst.CSTTransformer):
    """Rewrite uses of indirect imports.

    This will replace imports and attribute accesses using indirect references
    with their direct counterparts.
    """

    def __init__(self, imports_with_indirects, indirect_references):
        """Create an `RewriteIndirectImportsTransformer` instance.

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
    ) -> Union[cst.Import, cst.RemovalSentinel]:
        # TODO: Replace with direct import.
        # imports_with_indirects
        breakpoint()
        return updated_node  # .with_changes(names=names_to_keep)

    def leave_ImportFrom(
        self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> Union[cst.ImportFrom, cst.RemovalSentinel]:
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
                    module_fullnames = [
                        cst.helpers.get_full_name_for_node(m.name) for m in node.names
                    ]
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
                        ref_fullname = cst.helpers.get_full_name_for_node(
                            ref_parent_node
                        )
                        replacement_module = rewrites.get(ref_fullname)
                        if replacement_module:
                            indirect_references[ref_parent_node] = replacement_module

    return imports_with_indirects, indirect_references


def collect_indirect_references(project_path):

    project_path = Path(project_path)
    pkg_info = PythonPackageInfo(project_path)
    rewrites = {}

    # 1) Find package-level imports that introduce indirect references
    for pkg_name, pkg_path in pkg_info.packages_to_paths.items():
        pkg_init_src = (pkg_path / "__init__.py").read_text()
        pkg_init_cst = cst.parse_module(pkg_init_src)

        # TODO: This should be a transformer that also removes the indirect references, no?
        import_visitor = IndirectImportTransformer(pkg_info, pkg_path, rewrites)

        _ = pkg_init_cst.visit(import_visitor)

    # 2) Visit each module and replace all the indirect references and imports
    for mod_path, mod_info in pkg_info.filenames_to_modules:
        if mod_info.ispkg:
            mod_path
            continue

        mod_src = Path(mod_path).read_text()
        mod_cst = cst.parse_module(mod_src)

        wrapper = cst.metadata.MetadataWrapper(mod_cst)
        imports_with_indirects, indirect_references = refine_indirect_references(
            wrapper, rewrites
        )

        fixed_module = wrapper.module.visit(
            RewriteIndirectImportsTransformer(
                imports_with_indirects, indirect_references
            )
        )

        # Use difflib to show the changes
        import difflib

        print(
            "".join(
                difflib.unified_diff(
                    mod_src.splitlines(1), fixed_module.code.splitlines(1)
                )
            )
        )

        # if not fixed_module.deep_equals(mod_cst):
        #     pass  # write to file
