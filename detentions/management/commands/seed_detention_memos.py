"""Seed sample detention memos with multiple goods lines (and matching warehouse stock)."""

from django.core.management.base import BaseCommand
from django.db import transaction

from detentions.models import DetentionMemo, DetentionMemoGoodsLine
from warehouse.models import WarehouseStockItem

SAMPLE_MEMOS = [
    {
        "case_no": "SZ-2026-101",
        "reference_number": "DET-REF-2026-101",
        "fir_number": "FIR-PSH-441/2026",
        "date_time_occurrence": "2026-05-15 14:30",
        "place_of_occurrence": "Torkham Border, Khyber Pakhtunkhwa",
        "date_time_detention": "2026-05-15 16:00",
        "place_of_detention": "Customs House Peshawar",
        "detention_type": "Seizure",
        "directorate": "MCC Peshawar",
        "reason_for_detention": "Undeclared electronic goods",
        "location_of_detention": "PESHAWAR",
        "where_deposited": "Bonded Godown A, Peshawar",
        "settlement_status": "Pending",
        "verification_status": "Verified",
        "disposition_status": "In Warehouse",
        "owner_name": "Ali Trading Co.",
        "owner_cnic": "17101-1234567-1",
        "brief_facts": "Consignment of laptops and accessories seized for misdeclaration of value.",
        "goods": [
            {
                "qr": "QR-DET-2026-101-A",
                "description": "Laptop computers (HP ProBook 450)",
                "pct": "8471.3010",
                "qty": "120",
                "unit": "PCS",
                "condition": "Seized",
                "value": "2400000",
            },
            {
                "qr": "QR-DET-2026-101-B",
                "description": "Mobile phones (Samsung Galaxy A series)",
                "pct": "8517.1200",
                "qty": "350",
                "unit": "PCS",
                "condition": "Seized",
                "value": "8750000",
            },
            {
                "qr": "QR-DET-2026-101-C",
                "description": "Laptop chargers and power adapters",
                "pct": "8504.4090",
                "qty": "500",
                "unit": "PCS",
                "condition": "Seized",
                "value": "750000",
            },
        ],
    },
    {
        "case_no": "SZ-2026-102",
        "reference_number": "DET-REF-2026-102",
        "fir_number": "FIR-KHT-218/2026",
        "date_time_occurrence": "2026-05-20 09:15",
        "place_of_occurrence": "Kohat Customs Station",
        "date_time_detention": "2026-05-20 11:30",
        "place_of_detention": "Transit Shed B, Kohat",
        "detention_type": "Detention",
        "directorate": "MCC Kohat",
        "reason_for_detention": "Prohibited textile imports",
        "location_of_detention": "KOHAT",
        "where_deposited": "Transit Shed B, Kohat",
        "settlement_status": "Pending",
        "verification_status": "Verified",
        "disposition_status": "In Warehouse",
        "owner_name": "Khyber Textiles Ltd",
        "owner_cnic": "16101-9876543-2",
        "brief_facts": "Undeclared cotton fabric and dye chemicals detained at examination.",
        "goods": [
            {
                "qr": "QR-DET-2026-102-A",
                "description": "Cotton fabric rolls, printed",
                "pct": "5208.5200",
                "qty": "2500",
                "unit": "MTR",
                "condition": "Detained",
                "value": "1250000",
            },
            {
                "qr": "QR-DET-2026-102-B",
                "description": "Polyester yarn cones",
                "pct": "5402.4410",
                "qty": "800",
                "unit": "KGS",
                "condition": "Detained",
                "value": "960000",
            },
            {
                "qr": "QR-DET-2026-102-C",
                "description": "Industrial dye chemicals (liquid)",
                "pct": "3204.1710",
                "qty": "45",
                "unit": "KGS",
                "condition": "Detained",
                "value": "225000",
            },
            {
                "qr": "QR-DET-2026-102-D",
                "description": "Finished T-shirts, assorted sizes",
                "pct": "6109.1000",
                "qty": "1200",
                "unit": "PCS",
                "condition": "Detained",
                "value": "480000",
            },
        ],
    },
    {
        "case_no": "SZ-2026-103",
        "reference_number": "DET-REF-2026-103",
        "fir_number": "FIR-NSR-089/2026",
        "date_time_occurrence": "2026-06-01 08:00",
        "place_of_occurrence": "Nowshera Check Post",
        "date_time_detention": "2026-06-01 10:45",
        "place_of_detention": "Bonded Godown C, Nowshera",
        "detention_type": "Seizure",
        "directorate": "MCC Nowshera",
        "reason_for_detention": "Restricted pharmaceutical imports",
        "location_of_detention": "NOWSHERA",
        "where_deposited": "Bonded Godown C, Nowshera",
        "settlement_status": "Pending",
        "verification_status": "Verified",
        "disposition_status": "In Warehouse",
        "owner_name": "MediCare Imports",
        "owner_cnic": "17301-5551234-3",
        "brief_facts": "Medicaments and health supplements seized without valid import license.",
        "goods": [
            {
                "qr": "QR-DET-2026-103-A",
                "description": "Antibiotic tablets (Amoxicillin 500mg)",
                "pct": "3004.9090",
                "qty": "5000",
                "unit": "PCS",
                "condition": "Seized",
                "value": "1500000",
            },
            {
                "qr": "QR-DET-2026-103-B",
                "description": "Surgical face masks (3-ply)",
                "pct": "6307.9010",
                "qty": "10000",
                "unit": "PCS",
                "condition": "Seized",
                "value": "500000",
            },
            {
                "qr": "QR-DET-2026-103-C",
                "description": "Vitamin C supplement bottles",
                "pct": "2106.9090",
                "qty": "600",
                "unit": "PCS",
                "condition": "Seized",
                "value": "360000",
                "perishable": True,
            },
        ],
    },
]


class Command(BaseCommand):
    help = "Seed 3 sample detention memos with multiple goods lines and warehouse stock rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Create memos even if sample case numbers already exist.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        force = options["force"]
        created_memos = 0
        created_lines = 0
        created_stock = 0

        for entry in SAMPLE_MEMOS:
            case_no = entry["case_no"]
            if not force and DetentionMemo.objects.filter(case_no=case_no).exists():
                self.stdout.write(f"Skipping {case_no} (already exists).")
                continue

            memo = DetentionMemo.objects.create(
                case_no=case_no,
                reference_number=entry["reference_number"],
                fir_number=entry["fir_number"],
                date_time_occurrence=entry["date_time_occurrence"],
                place_of_occurrence=entry["place_of_occurrence"],
                date_time_detention=entry["date_time_detention"],
                place_of_detention=entry["place_of_detention"],
                detention_type=entry["detention_type"],
                directorate=entry["directorate"],
                reason_for_detention=entry["reason_for_detention"],
                location_of_detention=entry["location_of_detention"],
                where_deposited=entry["where_deposited"],
                settlement_status=entry["settlement_status"],
                verification_status=entry["verification_status"],
                disposition_status=entry["disposition_status"],
                owner_name=entry["owner_name"],
                owner_cnic=entry["owner_cnic"],
                brief_facts=entry["brief_facts"],
                created_by="seed_detention_memos",
            )
            created_memos += 1

            for idx, goods in enumerate(entry["goods"], start=1):
                line = DetentionMemoGoodsLine.objects.create(
                    memo=memo,
                    client_line_id=f"line-{idx}",
                    qr_code_number=goods["qr"],
                    description=goods["description"],
                    pct_code=goods["pct"],
                    quantity=goods["qty"],
                    unit=goods["unit"],
                    condition=goods["condition"],
                    assessable_value_pkr=goods["value"],
                    perishable=goods.get("perishable", False),
                )
                created_lines += 1

                stock_id = f"stock-{case_no}-{idx}"
                if force or not WarehouseStockItem.objects.filter(client_row_id=stock_id).exists():
                    WarehouseStockItem.objects.update_or_create(
                        client_row_id=stock_id,
                        defaults={
                            "detention_memo_id": memo.pk,
                            "case_ref": case_no,
                            "qr_code": goods["qr"],
                            "description": goods["description"],
                            "pct_code": goods["pct"],
                            "quantity": goods["qty"],
                            "unit": goods["unit"],
                            "godown_warehouse": entry["where_deposited"],
                            "status": "In Custody",
                        },
                    )
                    created_stock += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {case_no} ({memo.pk}) with {len(entry['goods'])} goods lines."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {created_memos} memo(s), {created_lines} goods line(s), {created_stock} stock row(s)."
            )
        )
