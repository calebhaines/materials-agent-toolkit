"""Bounded, in-memory CIF structure analysis through the optional ASE adapter."""

from __future__ import annotations

import math
import re
import warnings
from collections import Counter
from io import StringIO
from typing import Annotated, Any

import numpy as np
import periodictable
from pydantic import Field, StringConstraints, field_validator, model_validator

from ..contracts import CalculationResult, MissingOptionalDependencyError, StrictModel, ToolSpec
from .composition import AVOGADRO_CONSTANT_PER_MOL, _atomic_weights_source, _mass_warnings

MAX_ASYMMETRIC_SITES = 256
MAX_EXPANDED_ATOMS = 2048
OCCUPANCY_UNITY_TOLERANCE = 1e-8
SYMMETRY_SITE_TOLERANCE = 1e-8
MAX_CELL_CONDITION = 1e8
_ELEMENTS = {element.symbol: element for element in periodictable.elements if element.number > 0}
_FRACTIONAL_TAGS = ("_atom_site_fract_x", "_atom_site_fract_y", "_atom_site_fract_z")
_CARTESIAN_TAGS = ("_atom_site_cartn_x", "_atom_site_cartn_y", "_atom_site_cartn_z")
_SYMMETRY_TAGS = (
    "_space_group_symop_operation_xyz",
    "_space_group_symop.operation_xyz",
    "_symmetry_equiv_pos_as_xyz",
)
_SPACEGROUP_NUMBER_TAGS = (
    "_space_group.it_number",
    "_space_group_it_number",
    "_symmetry_int_tables_number",
)
_SPACEGROUP_NAME_TAGS = ("_space_group_name_h-m_alt", "_symmetry_space_group_name_h-m")
_PATTERSON_TAGS = ("_space_group.patterson_name_h-m",)
SYMMETRY_OPERATION_TOLERANCE = 1e-8

CifText = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100_000)]
ElementSymbol = Annotated[
    str, StringConstraints(strict=True, min_length=1, max_length=2, pattern=r"^[A-Z][a-z]?$")
]
AtomCount = Annotated[int, Field(strict=True, gt=0, le=MAX_EXPANDED_ATOMS)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
PositiveFiniteFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
FractionalCoordinate = Annotated[float, Field(ge=0, lt=1, allow_inf_nan=False)]
Vector3 = Annotated[list[FiniteFloat], Field(min_length=3, max_length=3)]
FractionalVector3 = Annotated[list[FractionalCoordinate], Field(min_length=3, max_length=3)]


class CifStructureInput(StrictModel):
    cif_text: CifText = Field(
        description=(
            "CIF 1.x text containing exactly one structural data block; nonstructural "
            "metadata blocks are allowed. At most 100000 characters, 256 asymmetric "
            "sites and 2048 expanded atoms. No file paths or network fetching. "
            "A complete three-dimensional cell and full natural-element occupancy "
            "are required; partial, mixed, unknown and isotope occupancies are unsupported."
        )
    )


class CifStructureOutput(StrictModel):
    atom_count: AtomCount = Field(
        description="Number of atoms in the symmetry-expanded supplied cell."
    )
    atomic_counts: dict[ElementSymbol, AtomCount] = Field(
        min_length=1,
        max_length=118,
        description="Full-cell elemental counts, ordered by atomic number.",
    )
    symbols: list[ElementSymbol] = Field(
        min_length=1,
        max_length=MAX_EXPANDED_ATOMS,
        description="Canonical natural-element symbol for each output site, in ASE expansion order.",
    )
    cell_vectors_angstrom: Annotated[list[Vector3], Field(min_length=3, max_length=3)] = Field(
        description="Three lattice vectors a, b, c as rows, in angstroms, in ASE's cell orientation."
    )
    fractional_positions: list[FractionalVector3] = Field(
        min_length=1,
        max_length=MAX_EXPANDED_ATOMS,
        description="Dimensionless coordinates in output symbol order, wrapped to [0,1).",
    )
    cartesian_positions_angstrom: list[Vector3] = Field(
        min_length=1,
        max_length=MAX_EXPANDED_ATOMS,
        description="Wrapped Cartesian site coordinates in angstroms: fractional row @ cell rows.",
    )
    cell_volume_angstrom3: PositiveFiniteFloat = Field(
        description="Positive supplied-cell volume in Å³."
    )
    density_kg_m3: PositiveFiniteFloat = Field(
        description="Ideal full-occupancy crystallographic density in kg/m³, using periodictable masses."
    )
    atomic_weights_source: str = Field(
        description="Atomic-weight library and installed version used."
    )
    source_block: str = Field(description="CIF data block name, without the data_ prefix.")

    @field_validator("symbols", "atomic_counts")
    @classmethod
    def natural_elements(cls, values: list[str] | dict[str, int]):
        if set(values) - _ELEMENTS.keys():
            raise ValueError("Only canonical natural-element symbols are supported")
        return values

    @model_validator(mode="after")
    def consistent_sites(self):
        if any(
            len(values) != self.atom_count
            for values in (
                self.symbols,
                self.fractional_positions,
                self.cartesian_positions_angstrom,
            )
        ):
            raise ValueError("Output site arrays must match atom_count")
        if dict(Counter(self.symbols)) != self.atomic_counts:
            raise ValueError("Output symbols must match atomic_counts")
        return self


def _numeric(value: Any, label: str) -> float:
    # ASE's CIF parser already handles numeric uncertainty notation such as 4.05(1).
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a known numeric CIF value")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _column(block: Any, tag: str, length: int | None = None) -> list[Any]:
    value = block.get(tag)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{tag} must be a nonempty atom-site loop column")
    if length is not None and len(value) != length:
        raise ValueError("Atom-site loop columns must have equal lengths")
    return value


def _validate_sites(block: Any) -> tuple[list[str], np.ndarray, bool]:
    symbol_tag = (
        "_atom_site_type_symbol" if "_atom_site_type_symbol" in block else "_atom_site_label"
    )
    raw_symbols = _column(block, symbol_tag)
    count = len(raw_symbols)
    if count > MAX_ASYMMETRIC_SITES:
        raise ValueError("CIF contains more than 256 asymmetric input sites")
    symbols = []
    for value in raw_symbols:
        if not isinstance(value, str):
            raise ValueError("Atom symbols or labels must be known strings")
        if symbol_tag == "_atom_site_type_symbol":
            symbol = value
        else:
            # Standard labels may append identifiers; ASE searches anywhere in a
            # label, which can silently turn an isotope/charge alias into an element.
            match = re.fullmatch(r"([A-Z][a-z]?)(?:[0-9]+[A-Za-z0-9_]*|_[A-Za-z0-9_]+)?", value)
            if match is None:
                raise ValueError(
                    "Atom labels must start with a canonical symbol and optional identifier"
                )
            symbol = match.group(1)
        if symbol not in _ELEMENTS:
            raise ValueError(
                "Only canonical natural-element symbols are supported; D/T isotopes are excluded"
            )
        symbols.append(symbol)

    fractional_present = [tag in block for tag in _FRACTIONAL_TAGS]
    cartesian_present = [tag in block for tag in _CARTESIAN_TAGS]
    if any(fractional_present) and not all(fractional_present):
        raise ValueError("All three fractional coordinate columns are required")
    if any(cartesian_present) and not all(cartesian_present):
        raise ValueError("All three Cartesian coordinate columns are required")
    if not all(fractional_present) and not all(cartesian_present):
        raise ValueError("CIF must provide three fractional or Cartesian coordinate columns")
    coords = None
    for tags, present in (
        (_CARTESIAN_TAGS, cartesian_present),
        (_FRACTIONAL_TAGS, fractional_present),
    ):
        if all(present):
            coords = np.array(
                [[_numeric(value, tag) for value in _column(block, tag, count)] for tag in tags]
            ).T
    assert coords is not None

    occupancy_normalized = False
    if "_atom_site_occupancy" in block:
        for raw_occupancy in _column(block, "_atom_site_occupancy", count):
            occupancy = _numeric(raw_occupancy, "Atom-site occupancy")
            if abs(occupancy - 1.0) > OCCUPANCY_UNITY_TOLERANCE:
                raise ValueError(
                    "Only full site occupancies within absolute tolerance 1e-8 of one are supported"
                )
            occupancy_normalized |= occupancy != 1.0
    for tag in ("_atom_site_disorder_group", "_atom_site_disorder_assembly"):
        if tag in block and any(value not in (".", 0, "0") for value in _column(block, tag, count)):
            raise ValueError("Disordered atom-site groups or assemblies are unsupported")
    return symbols, coords, occupancy_normalized


def _validate_cell(block: Any) -> np.ndarray:
    cellpar = block.get_cellpar()
    if cellpar is None:
        raise ValueError("CIF must contain all six three-dimensional cell parameters")
    numbers = [_numeric(value, "Cell parameter") for value in cellpar]
    if any(not 1e-6 <= value <= 1e6 for value in numbers[:3]):
        raise ValueError("Cell lengths must be between 1e-6 and 1e6 angstroms")
    if any(not 0 < value < 180 for value in numbers[3:]):
        raise ValueError("Cell angles must lie strictly between 0 and 180 degrees")
    alpha, beta, gamma = (math.radians(value) for value in numbers[3:])
    cosine = [math.cos(alpha), math.cos(beta), math.cos(gamma)]
    gram = np.array(
        [[1.0, cosine[2], cosine[1]], [cosine[2], 1.0, cosine[0]], [cosine[1], cosine[0], 1.0]]
    )
    if np.linalg.eigvalsh(gram)[0] <= 0:
        raise ValueError("Cell angles do not define a positive-definite three-dimensional geometry")
    cell = np.asarray(block.get_cell(), dtype=float)
    if cell.shape != (3, 3) or not np.isfinite(cell).all():
        raise ValueError("CIF must define a finite three-dimensional cell")
    singular_values = np.linalg.svd(cell, compute_uv=False)
    if singular_values[-1] <= 0 or singular_values[0] / singular_values[-1] > MAX_CELL_CONDITION:
        raise ValueError("Cell is singular or numerically unstable (condition number exceeds 1e8)")
    return cell


def _validate_symmetry_text(operation: Any) -> None:
    if not isinstance(operation, str):
        raise ValueError("Symmetry operations must be known coordinate-expression strings")
    components = re.sub(r"\s+", "", operation.lower()).split(",")
    term = r"(?:[xyz]|(?:\d+(?:\.\d*)?|\.\d+)(?:/\d+(?:\.\d*)?)?)"
    pattern = re.compile(rf"[+-]?{term}(?:[+-]{term})*", re.ASCII)
    if len(components) != 3 or any(
        pattern.fullmatch(component) is None for component in components
    ):
        raise ValueError("Unsupported or malformed CIF symmetry operation")
    for component in components:
        coordinates = re.findall(r"[xyz]", component)
        numeric_terms = re.findall(r"(?:\d+(?:\.\d*)?|\.\d+)(?:/\d+(?:\.\d*)?)?", component)
        if len(coordinates) != len(set(coordinates)) or len(numeric_terms) > 1:
            raise ValueError(
                "Symmetry expressions may use each coordinate once and at most one translation"
            )


def _operation_groups(operations: list[Any]) -> dict[tuple[int, ...], tuple[np.ndarray, Any]]:
    from scipy.spatial import cKDTree

    translations: dict[tuple[int, ...], list[np.ndarray]] = {}
    for rotation, translation in operations:
        key = tuple(int(value) for value in rotation.flat)
        translations.setdefault(key, []).append(np.mod(translation, 1.0))
    groups = {}
    for key, values in translations.items():
        unique = np.unique(np.array(values), axis=0)
        tree = cKDTree(unique, boxsize=1.0)
        if len(unique) > 1 and np.any(
            tree.query(unique, k=2, p=np.inf)[0][:, 1] <= SYMMETRY_OPERATION_TOLERANCE
        ):
            raise ValueError(
                "Distinct symmetry operations are too close within translation tolerance 1e-8"
            )
        groups[key] = unique, tree
    return groups


def _same_operations(left: dict, right: dict) -> bool:
    if left.keys() != right.keys():
        return False
    for key in left:
        left_translations, left_tree = left[key]
        right_translations, right_tree = right[key]
        if len(left_translations) != len(right_translations):
            return False
        left_distances, left_matches = left_tree.query(right_translations, p=np.inf)
        right_distances, right_matches = right_tree.query(left_translations, p=np.inf)
        if (
            np.any(left_distances > SYMMETRY_OPERATION_TOLERANCE)
            or np.any(right_distances > SYMMETRY_OPERATION_TOLERANCE)
            or len(np.unique(left_matches)) != len(left_matches)
            or len(np.unique(right_matches)) != len(right_matches)
        ):
            return False
    return True


def _validate_group_closure(groups: dict) -> None:
    # Composition (R_i,t_i)(R_j,t_j) = (R_i R_j, R_i t_j + t_i).
    # Group by exact integer rotations and query periodic translations using
    # SciPy's bounded spatial index. No pairwise 2048x2048x3 allocation is made.
    for left_key, (left_translations, _) in groups.items():
        left_rotation = np.array(left_key).reshape(3, 3)
        for right_key, (right_translations, _) in groups.items():
            right_rotation = np.array(right_key).reshape(3, 3)
            result_key = tuple(int(value) for value in (left_rotation @ right_rotation).flat)
            if result_key not in groups:
                raise ValueError("Supplied symmetry operations are not closed under composition")
            result_tree = groups[result_key][1]
            transformed = right_translations @ left_rotation.T
            chunk_size = max(1, 65_536 // len(right_translations))
            for offset in range(0, len(left_translations), chunk_size):
                composed = np.mod(
                    left_translations[offset : offset + chunk_size, None, :] + transformed,
                    1.0,
                ).reshape(-1, 3)
                distances = result_tree.query(composed, p=np.inf)[0]
                if np.any(distances > SYMMETRY_OPERATION_TOLERANCE):
                    raise ValueError(
                        "Supplied symmetry operations are not closed under composition"
                    )


def _spacegroup(block: Any, count: int, cell: np.ndarray):
    from ase.spacegroup.spacegroup import spacegroup_from_data

    declared = []
    excluded = {*_SPACEGROUP_NUMBER_TAGS, *_SPACEGROUP_NAME_TAGS, *_SYMMETRY_TAGS, *_PATTERSON_TAGS}
    base_tags = {key: value for key, value in block.items() if key not in excluded}
    if "_symmetry_space_group_setting" in block:
        setting = block["_symmetry_space_group_setting"]
        if isinstance(setting, str) and setting in ("1", "2"):
            setting = int(setting)
        if _numeric(setting, "Space-group setting") not in (1.0, 2.0):
            raise ValueError("Space-group setting must be one or two")
        base_tags["_symmetry_space_group_setting"] = int(setting)
    for tag in _SPACEGROUP_NUMBER_TAGS:
        if tag in block:
            raw_number = block[tag]
            if isinstance(raw_number, str) and re.fullmatch(r"\d{1,3}", raw_number):
                raw_number = int(raw_number)
            number = _numeric(raw_number, "Space-group number")
            if not number.is_integer() or not 1 <= number <= 230:
                raise ValueError("Space-group numbers must be integers from 1 to 230")
            declared.append(
                type(block)(block.name, {**base_tags, tag: int(number)}).get_spacegroup(True)
            )
    for tag in _SPACEGROUP_NAME_TAGS:
        if tag in block:
            if not isinstance(block[tag], str) or block[tag] in (".", "?"):
                raise ValueError("Space-group names must be known Hermann-Mauguin strings")
            declared.append(
                type(block)(block.name, {**base_tags, tag: block[tag]}).get_spacegroup(True)
            )
    canonical_groups = [_operation_groups(group.get_symop()) for group in declared]
    if canonical_groups and any(
        not _same_operations(canonical_groups[0], other) for other in canonical_groups[1:]
    ):
        raise ValueError("Declared space-group numbers and names conflict")
    supplied = []
    for tag in _SYMMETRY_TAGS:
        if tag in block:
            operations = block[tag] if isinstance(block[tag], list) else [block[tag]]
            if not operations or len(operations) * count > MAX_EXPANDED_ATOMS:
                raise ValueError("Asymmetric sites times symmetry operations must be at most 2048")
            for operation in operations:
                _validate_symmetry_text(operation)
            # A P1 template is a neutral carrier for an explicitly supplied
            # operation list; it does not add implied inversions/translations.
            supplied.append(
                spacegroup_from_data(
                    no=1,
                    setting=1,
                    centrosymmetric=False,
                    subtrans=[(0.0, 0.0, 0.0)],
                    sitesym=operations,
                )
            )
    if not declared and not supplied and any(tag in block for tag in _PATTERSON_TAGS):
        raise ValueError("A Patterson-group name alone does not specify the structure space group")
    spacegroup = (
        supplied[0]
        if supplied
        else (declared[0] if declared else type(block)(block.name, base_tags).get_spacegroup(True))
    )
    operations = spacegroup.get_symop()
    if not operations or count * len(operations) > MAX_EXPANDED_ATOMS:
        raise ValueError("Asymmetric sites times symmetry operations must be at most 2048")
    metric = cell @ cell.T
    scale = float(np.max(np.abs(metric)))
    identity_present = False
    for rotation, translation in operations:
        if not np.isfinite(rotation).all() or not np.isfinite(translation).all():
            raise ValueError("Symmetry operations must be finite")
        determinant = float(np.linalg.det(rotation))
        if abs(abs(determinant) - 1.0) > 1e-8:
            raise ValueError("Symmetry operations must have nonsingular unimodular rotations")
        if not np.allclose(rotation.T @ metric @ rotation, metric, rtol=0, atol=1e-8 * scale):
            raise ValueError("Symmetry operations are inconsistent with the supplied cell metric")
        wrapped_translation = np.mod(translation + 0.5, 1.0) - 0.5
        identity_present |= np.array_equal(rotation, np.eye(3)) and np.all(
            np.abs(wrapped_translation) <= SYMMETRY_OPERATION_TOLERANCE
        )
    if not identity_present:
        raise ValueError("The supplied symmetry operations must include the identity operation")
    if supplied:
        operation_groups = _operation_groups(operations)
        _validate_group_closure(operation_groups)
        if canonical_groups and not _same_operations(operation_groups, canonical_groups[0]):
            raise ValueError(
                "Supplied symmetry operations do not match the declared ASE standard setting and origin"
            )
        if any(
            not _same_operations(operation_groups, _operation_groups(other.get_symop()))
            for other in supplied[1:]
        ):
            raise ValueError("Supplied symmetry-operation aliases conflict")
    # Matching tolerances must not perturb canonical special positions: a
    # 1e-8 shifted inversion can otherwise split the origin into two ASE sites.
    return (declared[0] if declared and supplied else spacegroup), bool(declared and supplied)


def _reject_duplicate_tags(cif_text: str) -> None:
    seen: set[str] = set()
    in_text = False
    for line in cif_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(";"):
            in_text = not in_text
            continue
        if in_text or not stripped or stripped.startswith("#"):
            continue
        token = stripped.split(maxsplit=1)[0].lower()
        if token.startswith("data_"):
            seen.clear()
        elif token.startswith("_"):
            if token in seen:
                raise ValueError("Duplicate CIF data tags within a block are unsupported")
            seen.add(token)


def _analyze_block(block: Any, crystal: Any) -> tuple[CifStructureOutput, list[str]]:
    symbols, coords, occupancy_normalized = _validate_sites(block)
    cell = _validate_cell(block)
    spacegroup, symmetry_normalized = _spacegroup(block, len(symbols), cell)
    if all(tag in block for tag in _FRACTIONAL_TAGS):
        fractional = np.mod(coords, 1.0)
        if all(tag in block for tag in _CARTESIAN_TAGS):
            cartesian_input = np.array(
                [[_numeric(value, tag) for value in block[tag]] for tag in _CARTESIAN_TAGS]
            ).T
            cartesian_fractional = np.linalg.solve(cell.T, cartesian_input.T).T
            difference = np.mod(cartesian_fractional - fractional + 0.5, 1.0) - 0.5
            if not np.all(np.abs(difference) <= SYMMETRY_SITE_TOLERANCE):
                raise ValueError("Supplied fractional and Cartesian coordinates are inconsistent")
    else:
        fractional = np.mod(np.linalg.solve(cell.T, coords.T).T, 1.0)
    if not np.isfinite(fractional).all():
        raise ValueError("Atomic coordinates cannot be converted into finite fractional positions")
    atoms = crystal(
        symbols=symbols,
        basis=fractional,
        spacegroup=spacegroup,
        cell=cell,
        onduplicates="error",
        symprec=SYMMETRY_SITE_TOLERANCE,
        primitive_cell=False,
    )
    atom_count = len(atoms)
    if not 0 < atom_count <= MAX_EXPANDED_ATOMS:
        raise ValueError("The expanded supplied cell must contain 1 to 2048 atoms")
    expanded_symbols = atoms.get_chemical_symbols()
    fractional = np.mod(atoms.get_scaled_positions(wrap=False), 1.0)
    cartesian = fractional @ cell
    if not np.isfinite(fractional).all() or not np.isfinite(cartesian).all():
        raise ValueError("Expanded atomic coordinates must be finite")
    volume = abs(float(np.linalg.det(cell)))
    counts = Counter(expanded_symbols)
    atomic_counts = dict(sorted(counts.items(), key=lambda item: _ELEMENTS[item[0]].number))
    molar_mass = math.fsum(
        count * float(_ELEMENTS[symbol].mass) for symbol, count in atomic_counts.items()
    )
    if not math.isfinite(volume) or volume <= 0 or not math.isfinite(molar_mass) or molar_mass <= 0:
        raise ValueError("Derived cell volume and atomic mass must be positive and finite")
    density = molar_mass * (1e27 / AVOGADRO_CONSTANT_PER_MOL) / volume
    if not math.isfinite(density) or density <= 0:
        raise ValueError("Derived crystallographic density must be positive and finite")
    result = CifStructureOutput(
        atom_count=atom_count,
        atomic_counts=atomic_counts,
        symbols=expanded_symbols,
        cell_vectors_angstrom=cell.tolist(),
        fractional_positions=fractional.tolist(),
        cartesian_positions_angstrom=cartesian.tolist(),
        cell_volume_angstrom3=volume,
        density_kg_m3=density,
        atomic_weights_source=_atomic_weights_source(),
        source_block=block.name,
    )
    notices = _mass_warnings()
    if occupancy_normalized:
        notices.append(
            "Site occupancies within absolute tolerance 1e-8 of one were normalized to full occupancy."
        )
    if symmetry_normalized:
        notices.append(
            "Supplied symmetry operations were matched to and normalized to ASE's standard "
            "setting and origin, using periodic componentwise translation tolerance 1e-8."
        )
    return result, notices


def analyze_cif(inputs: CifStructureInput) -> CalculationResult:
    try:
        from ase.io.cif import parse_cif
        from ase.spacegroup import crystal
    except ModuleNotFoundError as exc:
        if exc.name != "ase" and not (exc.name or "").startswith("ase."):
            raise
        raise MissingOptionalDependencyError(
            "structure.analyze_cif requires ASE; install materials-agent-toolkit[structures]"
        ) from exc
    if inputs.cif_text.lstrip().startswith("#\\#CIF_2.0"):
        raise ValueError("CIF 2.0 syntax is unsupported; supply a CIF 1.x structure")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        try:
            _reject_duplicate_tags(inputs.cif_text)
            blocks = list(parse_cif(StringIO(inputs.cif_text), reader="ase"))
            if any(
                str(warning.message).startswith(
                    ("Wrong number", "Duplicated loop tags", "Badly formed number")
                )
                for warning in captured
            ):
                raise ValueError(
                    "Malformed CIF loop rows, numbers or duplicate tags are unsupported"
                )
            # Do not let ASE silently ignore an incomplete atom-site block.
            structures = [
                block for block in blocks if any(tag.startswith("_atom_site_") for tag in block)
            ]
            if len(structures) != 1:
                raise ValueError("CIF must contain exactly one structural data block")
            with np.errstate(all="raise"):
                result, notices = _analyze_block(structures[0], crystal)
        except ImportError:
            raise
        except ValueError:
            raise
        except Exception as exc:
            # ASE's parser uses assertions and several implementation exceptions
            # for malformed files. They are input failures at this boundary.
            raise ValueError("Malformed or unsupported CIF structure") from exc
    parser_notices = [f"ASE CIF parser: {warning.message}" for warning in captured]
    return CalculationResult(result=result, warnings=notices + list(dict.fromkeys(parser_notices)))


TOOLS = (
    ToolSpec(
        name="structure.analyze_cif",
        description=(
            "Parse one bounded CIF 1.x structure in memory, expand supplied symmetry "
            "with ASE, validate the full-occupancy three-dimensional cell, and return "
            "wrapped coordinates, elemental counts, volume and crystallographic density. "
            "Requires the optional structures installation extra."
        ),
        input_model=CifStructureInput,
        output_model=CifStructureOutput,
        execute=analyze_cif,
        assumptions=(
            "CIF 1.x only; exactly one atom-site data block, with optional nonstructural metadata blocks.",
            "Only canonical natural-element symbols are accepted; D/T, isotope labels, charged type symbols and disordered sites are unsupported.",
            "Absent occupancy means one; explicit occupancies within absolute tolerance 1e-8 of one are normalized to one. Partial or unknown occupancy is rejected.",
            "At most 100000 CIF characters, 256 input sites, and 2048 expanded atoms; input sites times symmetry-operation count must also be at most 2048, including redundant operations.",
            "Cell lengths must be 1e-6 to 1e6 Å inclusive; angles strictly between 0 and 180 degrees and positive-definite geometry; cell singular-value condition number at most 1e8.",
            "ASE applies supplied symmetry in the supplied cell; no primitive-cell conversion, symmetry inference or phase identification is performed. Absent symmetry means identity P1.",
            "Symmetry rotations must be unimodular and preserve the cell metric within absolute tolerance 1e-8 times its largest entry; the identity operation must be present.",
            "Explicit symmetry operations must form a complete closed group modulo lattice translations, with componentwise periodic translation tolerance 1e-8 and exact integer rotations.",
            "Exact duplicate operations are ignored for group comparison but counted against the resource bound; distinct operations with the same rotation and periodic translations within 1e-8 are rejected.",
            "Declared space-group number/name aliases must agree. Supplied operation lists with declared group metadata must match ASE's standard setting and origin; alternative origins are rejected rather than inferred. Supplied operation lists without group metadata are supported without assigning a space-group identity.",
            "Supplied operations matching a declared group within periodic componentwise translation tolerance 1e-8 are normalized to that group's canonical ASE operations before expansion, preserving canonical special positions; the normalization is reported in warnings.",
            "Symmetry-equivalent repeated input sites and mixed sites are rejected using ASE's dimensionless componentwise site tolerance 1e-8.",
            "Cell vectors are rows in Å; positions are wrapped to [0,1), and Cartesian row = fractional row @ cell rows. Angles are interpreted in degrees.",
            "If both fractional and Cartesian input coordinate columns are present, they must agree modulo lattice translations within dimensionless component tolerance 1e-8; fractional coordinates are used for expansion.",
            "Density uses expanded elemental counts and periodictable masses, consistent with crystal.density; 1 Å³ = 1e-30 m³ and N_A = 6.02214076e23 mol^-1 exactly.",
            "Atomic weights use conventional terrestrial isotope abundances where available; library representative isotope masses are retained for other elements.",
            "CIF numeric uncertainty notation is parsed by ASE to its central value; measurement uncertainty, oxidation states, bonding and porosity are not inferred.",
            "Input is parsed in memory; no user-supplied paths are opened, no data is fetched and no external jobs are executed. ASE parser warnings are returned in the response envelope.",
        ),
        references=(
            "https://wiki.fysik.dtu.dk/ase/ase/io/formatoptions.html#cif",
            "https://wiki.fysik.dtu.dk/ase/ase/spacegroup/spacegroup.html",
            "https://www.iucr.org/resources/cif/spec/version1.1",
            "https://periodictable.readthedocs.io/en/latest/api/mass.html",
            "https://www.bipm.org/en/si-base-units/mole",
        ),
        dependencies=("ase", "numpy", "periodictable", "scipy"),
    ),
)
