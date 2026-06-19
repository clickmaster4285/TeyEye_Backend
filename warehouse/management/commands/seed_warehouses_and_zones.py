from django.core.management.base import BaseCommand
from warehouse.models import Warehouse, SiteZone
from warehouse.zone_catalog import CUSTOMS_WAREHOUSE_ZONES


class Command(BaseCommand):
    help = "Seed warehouses and zones for all Peshawar customs locations."

    def handle(self, *args, **options):
        # Define warehouses per location
        warehouses_data = [
            {
                "location_code": "PESHAWAR",
                "code": "WH-PSH-01",
                "name": "Peshawar Customs Warehouse",
            },
            {
                "location_code": "KOHAT",
                "code": "WH-KHT-01",
                "name": "Kohat Customs Warehouse",
            },
            {
                "location_code": "NOWSHERA",
                "code": "WH-NWS-01",
                "name": "Nowshera Customs Warehouse",
            },
            {
                "location_code": "MARDAN",
                "code": "WH-MRD-01",
                "name": "Mardan Customs Warehouse",
            },
            {
                "location_code": "DI_KHAN",
                "code": "WH-DIK-RETTA",
                "name": "New Warehouse, Retta Kulachi",
            },
        ]

        total_created = 0
        total_zones = 0

        for wh_data in warehouses_data:
            warehouse, created = Warehouse.objects.get_or_create(
                code=wh_data["code"],
                defaults={
                    "location_code": wh_data["location_code"],
                    "name": wh_data["name"],
                    "status": "ACTIVE",
                }
            )

            if created:
                total_created += 1
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Created warehouse: {warehouse.code} ({warehouse.location_code})")
                )
            else:
                self.stdout.write(f"  Warehouse exists: {warehouse.code}")

            # Ensure all 7 canonical zones exist for this warehouse
            for zone_def in CUSTOMS_WAREHOUSE_ZONES:
                zone, z_created = SiteZone.objects.get_or_create(
                    warehouse=warehouse,
                    code=zone_def["code"],
                    defaults={
                        "name": zone_def["name"],
                        "purpose": zone_def.get("purpose", ""),
                        "category": zone_def["category"],
                        "security_level": zone_def["security_level"],
                        "sort_order": zone_def["sort_order"],
                        "description": zone_def.get("description", ""),
                        "is_active": True,
                        "requires_escort": zone_def.get("requires_escort", False),
                        "vms_zone_type": zone_def.get("vms_zone_type", "Public"),
                        "access_hours_start": zone_def.get("access_hours_start", "06:00"),
                        "access_hours_end": zone_def.get("access_hours_end", "22:00"),
                        "weekend_access": zone_def.get("weekend_access", False),
                        "max_occupancy": zone_def.get("max_occupancy", 10),
                        "allowed_visitor_categories": zone_def.get("allowed_visitor_categories", []),
                        "gate_ids": zone_def.get("gate_ids", []),
                        "camera_ids": zone_def.get("camera_ids", []),
                    }
                )
                if z_created:
                    total_zones += 1
                else:
                    canonical_fields = {
                        "name": zone_def["name"],
                        "purpose": zone_def.get("purpose", ""),
                        "category": zone_def["category"],
                        "security_level": zone_def["security_level"],
                        "sort_order": zone_def["sort_order"],
                        "description": zone_def.get("description", ""),
                        "requires_escort": zone_def.get("requires_escort", False),
                        "vms_zone_type": zone_def.get("vms_zone_type", "Public"),
                        "access_hours_start": zone_def.get("access_hours_start", "06:00"),
                        "access_hours_end": zone_def.get("access_hours_end", "22:00"),
                        "weekend_access": zone_def.get("weekend_access", False),
                        "max_occupancy": zone_def.get("max_occupancy", 10),
                        "allowed_visitor_categories": zone_def.get("allowed_visitor_categories", []),
                        "gate_ids": zone_def.get("gate_ids", []),
                        "camera_ids": zone_def.get("camera_ids", []),
                    }
                    updated = False
                    for field, value in canonical_fields.items():
                        if getattr(zone, field) != value:
                            setattr(zone, field, value)
                            updated = True
                    if updated:
                        zone.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Seed complete!\n"
                f"  • Warehouses created: {total_created}\n"
                f"  • Total zones created: {total_zones}\n"
                f"  • Expected: {len(warehouses_data)} warehouses × 7 zones = {len(warehouses_data) * 7} zones"
            )
        )
