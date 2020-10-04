import pytest

import libcst as cst

from pathlib import Path
from textwrap import dedent
from dataclasses import dataclass

from refactors.direct_imports import (
    PythonPackageInfo,
    IndirectImportTransformer,
    # RewriteIndirectImportsTransformer,
    # refine_indirect_references,
    # collect_indirect_references,
)


@dataclass
class SampleProject:
    project_dir: Path
    module_to_expected_src: dict


@pytest.fixture
def sample_project(tmpdir):
    pkg_dir = Path(tmpdir) / "pkg"
    pkg_dir.mkdir()

    expected_src = {}

    pkg_init_file = pkg_dir / "__init__.py"
    pkg_init_file.write_text(
        dedent(
            r"""
    # This reference is direct(ish)
    import pkg.mod1

    # This reference is indirect
    import pkg.mod2 as module2

    # This reference is direct(ish)
    from . import mod2

    # These references are indirect
    from .mod1 import var1, var2 as variable2

    # These references are indirect
    from pkg.mod2 import var3 as variable3

    import pkg.sub_pkg.mod3 as mod3

    var0 = mod3.var4
    """
        )
    )

    exp_pkg_init_src = dedent(
        r"""
    # This reference is direct(ish)
    import pkg.mod1

    var0 = mod3.var4
    """
    )

    expected_src["pkg"] = exp_pkg_init_src

    mod1_file = pkg_dir / "mod1.py"
    mod1_file.write_text(
        dedent(
            r"""
    import pkg

    from pkg import mod2

    var1 = 1
    var2 = 2

    # This reference is direct
    print(pkg.mod1)

    # This reference is direct
    if pkg.var0 > 0:
        print("blah")

    # This reference is indirect
    print(pkg.mod3.var4.lower())

    # This reference is indirect
    x = pkg.var3 + 2
    """
        )
    )

    exp_pkg_mod1_src = dedent(
        r"""
    import pkg

    from pkg import mod2

    var1 = 1
    var2 = 2

    # This reference is direct
    print(pkg.mod1)

    # This reference is direct
    if pkg.var0 > 0:
        print("blah")

    # This reference is indirect
    print(pkg.sub_pkg.mod3.var4.lower())

    # This reference is indirect
    x = pkg.mod2.var3 + 2
    """
    )

    expected_src["pkg.mod1"] = exp_pkg_mod1_src

    mod2_file = pkg_dir / "mod2.py"
    mod2_file.write_text(
        dedent(
            r"""
    # These are indirect
    from pkg import variable2, variable1
    from pkg import var1
    from pkg.mod1 import var1 as blah1

    var3 = 3
    """
        )
    )

    exp_pkg_mod2_src = dedent(
        r"""
    # These are indirect
    from pkg.mod1 import var2 as variable2
    from pkg.mod1 import var1 as variable1
    from pkg.mod1 import var1
    from pkg.mod1 import var1 as blah1

    var3 = 3
    """
    )

    expected_src["pkg.mod2"] = exp_pkg_mod2_src

    sub_pkg_dir = pkg_dir / "sub_pkg"
    sub_pkg_dir.mkdir()

    sub_pkg_init_file = sub_pkg_dir / "__init__.py"
    sub_pkg_init_file.write_text(
        dedent(
            r"""
    # This reference is direct
    import pkg.mod1

    # This reference is indirect
    from .. import mod2

    # This reference is indirect
    from pkg import var1
    """
        )
    )

    exp_sub_pkg_init_src = dedent(
        r"""
    # This reference is direct
    import pkg.mod1
    """
    )

    expected_src["pkg.sub_pkg"] = exp_sub_pkg_init_src

    mod3_file = sub_pkg_dir / "mod3.py"
    mod3_file.write_text(
        dedent(
            r"""
    import pkg.sub_pkg as spkg

    # This reference is indirect
    for i in range(spkg.var1):
        print(i)

    var4 = "hi"
    """
        )
    )

    exp_pkg_sub_pkg_mod3_src = dedent(
        r"""
    import pkg.sub_pkg as spkg
    import pkg.mod1

    # This reference is indirect
    for i in range(pkg.mod1.var1):
        print(i)

    var4 = "hi"
    """
    )

    expected_src["pkg.sub_pkg.mod3"] = exp_pkg_sub_pkg_mod3_src

    return SampleProject(pkg_dir, expected_src)


def test_IndirectImportTransformer(sample_project):
    pkg_dir = sample_project.project_dir
    pkg_name = pkg_dir.stem

    pkg_init_cst = cst.parse_module((pkg_dir / "__init__.py").read_text())

    pkg_info = PythonPackageInfo(pkg_dir)

    rewrites = {}

    for pkg_name, pkg_path in pkg_info.packages_to_paths.items():
        pkg_init_path = pkg_path / "__init__.py"
        pkg_init_src = pkg_init_path.read_text()
        pkg_init_cst = cst.parse_module(pkg_init_src)

        import_visitor = IndirectImportTransformer(pkg_info, pkg_path, rewrites)

        modified_init = pkg_init_cst.visit(import_visitor)
        assert modified_init.code == sample_project.module_to_expected_src[pkg_name]

    exp_txt_rewrites = {
        "pkg.module2": "pkg.mod2",
        "pkg.var1": "mod1.var1",
        "pkg.variable2": "mod1.var2",
        "pkg.variable3": "pkg.mod2.var3",
        "pkg.mod3": "pkg.sub_pkg.mod3",
        "pkg.sub_pkg.mod2": "pkg.mod2",
        "pkg.sub_pkg.var1": "pkg.var1",
    }

    txt_rewrites = {k: pkg_init_cst.code_for_node(v) for k, v in rewrites.items()}

    assert exp_txt_rewrites == txt_rewrites
