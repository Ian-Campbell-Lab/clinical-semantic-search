"""
EHR data preprocessing -- reference implementation for Epic Clarity/Caboodle.

This module transforms raw EHR export columns into the standardized schema
expected by the embedding and indexing pipeline.  The key artifact is the
``col_mapper`` dictionary in ``MetadataTransformer``, which maps your EHR's
column names to the internal schema.

PORTING NOTE: The ``col_mapper`` below reflects Epic Clarity column names.
To adapt for a different EHR:

1. Update ``col_mapper`` keys to match your source column names.
2. Update ``datetime_data_dict`` with your date column formats.
3. Adjust ``__format_note_category()`` if your EHR represents note types
   differently (e.g., a single column instead of three).

The ``formatted_cols`` list defines the output schema.  All downstream
modules expect these column names.

Expected output columns:
    note_id, mrn, pat_name, pref_name, dob, age, date, note_category,
    author_name, author_type, encounter_type, department, specialty
"""

from abc import ABC, abstractmethod
from functools import partial

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta


# ── Age formatting ───────────────────────────────────────────────────

def compute_age_string(event_date, birth_date) -> str | None:
    """Compute an age string like ``"2 days"``, ``"5 months"``, or ``"4 years"``.

    Boundary rules match Epic's default .AGE SmartLink:
    - < 30 days  => days
    - >= 30 days and < 2 months => weeks
    - >= 2 months and < 3 years => months
    - >= 3 years => years
    """
    if pd.isnull(event_date) or pd.isnull(birth_date):
        return None
    if event_date < birth_date:
        return "Unborn"

    rd = relativedelta(event_date, birth_date)
    total_days = (event_date - birth_date).days
    total_weeks = total_days // 7
    total_months = rd.years * 12 + rd.months
    years = rd.years

    if years >= 3:
        return f"{years} year{'s' if years != 1 else ''}"
    if total_months >= 2:
        return f"{total_months} month{'s' if total_months != 1 else ''}"
    if total_days >= 30 and total_months < 2:
        return f"{total_weeks} week{'s' if total_weeks != 1 else ''}"
    return f"{total_days} day{'s' if total_days != 1 else ''}"


# ── Base transformer ────────────────────────────────────────────────

class DataTransformer(ABC):
    """Abstract base for data transformers in the preprocessing pipeline."""

    def __init__(self):
        self._data = None

    @abstractmethod
    def transform(self, data=None):
        raise NotImplementedError

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value

    def process(self, data=None):
        if data is None:
            self.transform()
        else:
            self.transform(data)
        return self._data


# ── Metadata transformer (Epic reference) ───────────────────────────

class MetadataTransformer(DataTransformer):
    """Transform raw EHR columns into the standardized internal schema.

    The ``col_mapper`` dictionary maps Epic Clarity column names to their
    internal equivalents.  Institutions using a different EHR should update
    the keys (left side) to match their source column names.
    """

    # Map source column names -> internal names.
    # UPDATE THE KEYS for your EHR system.
    col_mapper = {
        "pat_id": "pat_id",
        "pat_mrn_id": "pat_mrn_id",
        "pat_first_name": "pat_first_name",
        "pat_middle_name": "pat_middle_name",
        "pat_last_name": "pat_last_name",
        "preferred_name": "preferred_name",
        "birth_date": "birth_date",
        "sex": "sex",
        "note_id": "note_id",
        "note_contact_date": "note_contact_date",
        "encounter_contact_date": "encounter_contact_date",
        "hosp_admsn_time": "hosp_admsn_time",
        "contact_date_real": "contact_date_real",
        "enc_type": "enc_type",
        "dept_name": "dept_name",
        "author_prov_name": "author_prov_name",
        "prov_type": "prov_type",
        "author_service": "author_service",
        "create_instant_dttm": "create_instant_dttm",
        "lst_filed_inst_dttm": "lst_filed_inst_dttm",
        "date_of_servic_dttm": "date_of_servic_dttm",
        "note_type": "note_type",
        "note_type_noadd": "note_type_noadd",
        "ip_note_type": "ip_note_type",
        "note_text": "note_text",
    }

    # Output column names after transformation.
    formatted_cols = [
        "note_id", "mrn", "pat_name", "pref_name", "dob", "age",
        "date", "note_category", "author_name", "author_type",
        "encounter_type", "department", "specialty",
    ]

    # Date column format strings for parsing.
    datetime_data_dict = {
        "date_of_servic_dttm": "%Y-%m-%d %H:%M",
        "create_instant_dttm": "%Y-%m-%d %H:%M",
        "lst_filed_inst_dttm": "%Y-%m-%d %H:%M",
        "birth_date": "%Y-%m-%d",
        "note_contact_date": "%Y-%m-%d",
        "encounter_contact_date": "%Y-%m-%d",
        "hosp_admsn_time": "%Y-%m-%d %H:%M",
    }

    def __init__(self):
        super().__init__()

    def transform(self, data=None):
        if data is not None:
            self._data = data
        self._data = self._data.rename(columns={col: col.lower() for col in self._data.columns})
        self._validate_cols()
        self._data = self._data.rename(MetadataTransformer.col_mapper)
        self._parse_datetime()
        self._format_note_date()
        self._format_age()
        self._format_note_category()
        self._format_department()
        self._format_specialty()
        self._format_encounter_type()
        self._format_dob()
        self._create_pat_name()
        self._data["date"] = self._data["date"].dt.strftime("%m/%d/%Y")
        self._rename_formatted_cols()

    def _validate_cols(self):
        missing = set(MetadataTransformer.col_mapper.keys()) - set(self._data.columns)
        if missing:
            raise ValueError(f"Missing columns: {missing}")

    def _parse_datetime(self):
        for col, fmt in MetadataTransformer.datetime_data_dict.items():
            self._data[col] = pd.to_datetime(self._data[col], format=fmt)
            self._data[col] = self._data[col].astype("datetime64[s]")

    def _create_pat_name(self):
        for col in ("pat_first_name", "pat_middle_name", "pat_last_name"):
            self._data[col] = self._data[col].fillna("")
        self._data["pat_name"] = (
            self._data["pat_first_name"]
            .str.cat(self._data[["pat_middle_name", "pat_last_name"]], sep=" ")
            .str.replace("  ", " ")
            .str.strip()
        )

    def _format_department(self):
        self._data["department"] = self._data["dept_name"]

    def _format_specialty(self):
        self._data["specialty"] = self._data["author_service"]

    def _format_note_category(self):
        """Combine note_type, note_type_noadd, and ip_note_type into a single category.

        This logic handles Epic's three-tier note type system.  Institutions
        with a simpler note type model can replace this with a direct column
        assignment.
        """
        self._data["note_category"] = self._data["note_type"]
        self._data["note_category"] = self._data["note_category"].fillna(
            self._data["note_type_noadd"]
        )

        noadd_in_cat = np.char.find(
            self._data["note_category"].str.lower().values.astype(str),
            self._data["note_type_noadd"].str.lower().values.astype(str),
        ) != -1
        cat_in_noadd = np.char.find(
            self._data["note_type_noadd"].str.lower().values.astype(str),
            self._data["note_category"].str.lower().values.astype(str),
        ) != -1

        self._data.loc[cat_in_noadd, "note_category"] = self._data.loc[
            cat_in_noadd, "note_type_noadd"
        ]
        mask = ~noadd_in_cat & ~cat_in_noadd & ~self._data["note_type_noadd"].isna()
        self._data.loc[mask, "note_category"] = self._data.loc[
            mask, "note_category"
        ].str.cat(others=self._data.loc[mask, "note_type_noadd"], sep=",", na_rep="")

        self._data["note_category"] = self._data["note_category"].fillna(
            self._data["ip_note_type"]
        )
        ip_in_cat = np.char.find(
            self._data["note_category"].str.lower().values.astype(str),
            self._data["ip_note_type"].str.lower().values.astype(str),
        ) != -1
        cats_in_ip = (
            np.char.find(
                self._data["ip_note_type"].str.lower().values.astype(str),
                self._data["note_type_noadd"].str.lower().values.astype(str),
            ) != -1
        ) | (
            np.char.find(
                self._data["ip_note_type"].str.lower().values.astype(str),
                self._data["note_type"].str.lower().values.astype(str),
            ) != -1
        )

        mask = ~ip_in_cat & ~cats_in_ip & ~self._data["ip_note_type"].isna()
        self._data.loc[mask, "note_category"] = self._data.loc[
            mask, "note_category"
        ].str.cat(others=self._data.loc[mask, "ip_note_type"], sep=",", na_rep="")

    def _format_note_date(self):
        """Pick the best available date, in preference order."""
        self._data["date"] = self._data["date_of_servic_dttm"]
        for fallback in (
            "create_instant_dttm", "lst_filed_inst_dttm",
            "note_contact_date", "hosp_admsn_time", "encounter_contact_date",
        ):
            self._data["date"] = self._data["date"].fillna(self._data[fallback])

    def _format_age(self):
        self._data["age"] = self._data[["date", "birth_date"]].apply(
            lambda x: compute_age_string(x["date"], x["birth_date"]), axis=1
        )

    def _format_dob(self):
        month = self._data["birth_date"].dt.month.astype("str")
        day = self._data["birth_date"].dt.day.astype("str")
        year = self._data["birth_date"].dt.year.astype("str")
        self._data["dob"] = month.str.cat(others=[day, year], sep="/")

    def _format_encounter_type(self):
        self._data["encounter_type"] = self._data["enc_type"]

    def _rename_formatted_cols(self):
        self._data = self._data.rename(
            columns={
                "pat_mrn_id": "mrn",
                "author_prov_name": "author_name",
                "prov_type": "author_type",
                "preferred_name": "pref_name",
            }
        )


# ── Pipeline orchestrator ────────────────────────────────────────────

class PreprocessPipeline:
    """Chain multiple DataTransformers and apply them sequentially."""

    def __init__(self, data: pd.DataFrame, pipeline: list[DataTransformer]):
        self.pipeline = pipeline
        self.data = data

    def process(self) -> pd.DataFrame:
        for transformer in self.pipeline:
            transformer.data = self.data
            self.data = transformer.process()
        return self.data
