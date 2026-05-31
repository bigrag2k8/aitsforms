"""Shared data model for the ODOT title forms.

A single TitleJob backs BOTH the RE 46 (Title Report) and RE 46-1 (Title Chain).
The shared identifier fields (district / crs / parcel / pid / county)
are entered once and flow into both documents.
"""
from __future__ import annotations
from typing import List
from pydantic import BaseModel, Field


class ChainEntry(BaseModel):
    grantor: str = ""
    grantee: str = ""
    date_signed: str = ""
    date_recorded: str = ""
    volume_page: str = ""
    conveyance_fee: str = ""
    instrument_type: str = ""
    description: str = ""


class TaxEntry(BaseModel):
    aud_par_no: str = ""
    land: str = ""
    building: str = ""
    total: str = ""
    taxes: str = ""


class TitleJob(BaseModel):
    # --- shared identifiers (populate both forms) ---
    district: str = ""
    crs: str = ""
    parcel: str = ""
    pid: str = ""
    county: str = ""

    # --- RE 46 report metadata ---
    report_type: str = "42year"  # 42year | abbreviated | update

    # --- owner block ---
    owner_name: str = ""
    owner_marital: str = ""
    owner_interest: str = ""
    mail_addr1: str = ""
    mail_addr2: str = ""
    owner_phone: str = ""
    prop_addr1: str = ""
    prop_addr2: str = ""

    # --- description of premises ---
    fee_description: str = ""

    # --- (3-A) mortgages / liens ---
    mortgages_name: str = ""
    mortgages_date: str = ""
    mortgages_amount: str = ""

    # --- (3-B) leases ---
    leases_name: str = ""
    leases_type: str = ""
    leases_term: str = ""

    # --- (3-C) easements ---
    easements_name: str = ""
    easements_type: str = ""

    # --- (4) defects ---
    defects: str = ""

    # --- (5) taxes & special assessments ---
    township: str = ""
    school_district: str = ""
    taxes: List[TaxEntry] = Field(default_factory=list)

    # --- (6) CAUV ---
    cauv: bool = False
    cauv_comments: str = ""

    # --- certification block ---
    cover_from: str = ""
    cover_to: str = ""
    sign_datetime: str = ""
    agent_name: str = ""

    # --- update title block ---
    update_from: str = ""
    update_to: str = ""
    update_datetime: str = ""
    update_agent_name: str = ""
    update_comments: str = ""

    # --- title chain (RE 46-1) ---
    chain: List[ChainEntry] = Field(default_factory=list)

    def context(self) -> dict:
        """Jinja context for docxtpl (plain dicts/lists)."""
        return self.model_dump()
