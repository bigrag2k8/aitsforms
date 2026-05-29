"""Quick end-to-end smoke test: render both forms (DOCX + PDF) with sample data."""
from backend.models import TitleJob, ChainEntry, TaxEntry
from backend.generator import generate, find_soffice

job = TitleJob(
    district="06",
    crs="FRA-70-12.34",
    parcel="15",
    suffix="WD",
    pid="010-123456-00",
    county="Franklin",
    report_type="42year",
    owner_name="John Q. Public and Jane A. Public",
    owner_marital="Married to each other",
    owner_interest="Fee Simple",
    mail_addr1="123 Main Street",
    mail_addr2="Columbus, OH 43215",
    owner_phone="(614) 555-0100",
    prop_addr1="123 Main Street",
    prop_addr2="Columbus, OH 43215",
    fee_description="Being 1.234 acres out of Survey 456, as conveyed in OR Vol 1234 Pg 567.",
    mortgages_name="Acme Bank, 1 Bank Plaza, Columbus OH",
    mortgages_date="03/15/2019",
    mortgages_amount="$150,000.00 Mortgage",
    leases_name="N/A",
    leases_type="N/A",
    leases_term="N/A",
    easements_name="Columbia Gas, utility easement",
    easements_type="Utility",
    defects="None of record.",
    township="Franklin Township",
    school_district="Columbus City SD",
    taxes=[
        TaxEntry(aud_par_no="010-123456-00", land="40,000", building="120,000", total="160,000", taxes="3,250.00"),
        TaxEntry(aud_par_no="010-123457-00", land="15,000", building="0", total="15,000", taxes="410.00"),
    ],
    cauv=False,
    cauv_comments="Not enrolled.",
    cover_from="01/01/1977",
    cover_to="05/29/2026",
    sign_datetime="05/29/2026 10:30",
    agent_name="A. Title Agent",
    chain=[
        ChainEntry(grantor="Acme Developers LLC", grantee="John Q. Public", date_signed="03/10/2019",
                   date_recorded="03/15/2019 09:00", volume_page="1234/567", conveyance_fee="$450.00",
                   instrument_type="Warranty Deed", description="1.234 ac, Survey 456"),
        ChainEntry(grantor="First Owner", grantee="Acme Developers LLC", date_signed="06/01/2005",
                   date_recorded="06/03/2005 14:20", volume_page="0987/321", conveyance_fee="$300.00",
                   instrument_type="General Warranty Deed", description="Same premises, 1.234 ac"),
        ChainEntry(grantor="Original Grantor", grantee="First Owner", date_signed="08/20/1977",
                   date_recorded="08/25/1977", volume_page="0123/045", conveyance_fee="$60.00",
                   instrument_type="Warranty Deed", description="Original parcel"),
    ],
)

print("soffice:", find_soffice())
res = generate(job, job_id="SMOKE", want_pdf=True)
for k, v in res.items():
    print(f"{k}: {v}")
