"""
Complete Rocketlane Migration Tool - Properties-Based with Automations & Timesheets
Migrates fields, roles, skills, users, templates, dependencies, automations, and timesheets
Order: Fields -> Roles -> Skills -> Users -> Templates -> Dependencies -> Automations -> Timesheets

This version loads configuration from portal.properties file
"""

import requests
import json
import time
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from properties_loader import PropertiesLoader


class CompleteMigratorWithProperties:
    """Complete migration tool using properties file configuration"""

    def __init__(self, properties_file: str = "portal.properties"):
        # Load configuration from properties file
        loader = PropertiesLoader(properties_file)
        self.portal1_config = loader.get_portal1_config()
        self.portal2_config = loader.get_portal2_config()
        self.migration_config = loader.get_migration_config()
        self.logging_config = loader.get_logging_config()
        self.rate_limits = loader.get_rate_limits()

        # Migration state
        self.migration_log = []
        self.field_mapping = {}
        self.section_mapping = {}  # Portal 1 section ID -> Portal 2 section ID
        self.role_mapping = {}
        self.skill_mapping = {}
        self.user_mapping = {}
        self.template_mapping = {}
        self.task_id_mapping = {}
        self.phase_id_mapping = {}
        self.automation_mapping = {}
        self.timesheet_mapping = {
            "configuration": {},
            "categories": {},
            "activities": {}
        }
        self.errors = []
        self.holiday_calendars = []
        self.created_sections = []  # sections actually created in Portal 2 this run
        # Mapping keys that came from a previous run's JSON rather than this run,
        # so the cloned-items report doesn't credit them to this run
        self.loaded_mapping_keys = {}

    def _make_request(self, method: str, url: str, headers: Dict, data: Optional[Dict] = None) -> Dict:
        """Make HTTP request with error handling"""
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=30)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=30)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return {
                "success": True,
                "status_code": response.status_code,
                "data": response.json() if response.content else {}
            }
        except requests.exceptions.RequestException as e:
            error_detail = {
                "success": False,
                "error": str(e),
                "status_code": getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
            }
            if hasattr(e, 'response') and e.response is not None and e.response.content:
                try:
                    error_detail["response_body"] = e.response.json()
                except:
                    error_detail["response_body"] = e.response.text
            return error_detail

    def log_operation(self, action: str, portal: str, url: str, response: Dict, **kwargs):
        """Log an operation"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "portal": portal,
            "url": url,
            "response": response,
            **kwargs
        }
        self.migration_log.append(log_entry)

        if not response.get("success"):
            self.errors.append(log_entry)

    # ==================== FIELDS MIGRATION ====================

    def get_all_fields_from_portal1(self) -> List[Dict]:
        """Fetch all fields from Portal 1"""
        print("\n   [1/5] Fetching all fields from Portal 1...")

        # Use /api/v1/all-fields which returns correct field types
        url = f"{self.portal1_config['v1_api_base']}{self.portal1_config['endpoints']['all_fields']}"
        headers = {"api-key": self.portal1_config['api_key']}

        response = self._make_request("GET", url, headers)
        self.log_operation("GET_ALL_FIELDS", "Portal 1", url, response)

        if response["success"]:
            # Handle different response formats dynamically
            data = response["data"]

            if isinstance(data, list):
                # Check if fields are nested (grouped format)
                if data and isinstance(data[0], dict) and "fields" in data[0] and not data[0].get("fieldId"):
                    # Flatten: data is array of {objectType, fields[]} - extract all fields
                    fields = []
                    for item in data:
                        if isinstance(item.get("fields"), list):
                            fields.extend(item["fields"])
                else:
                    # Flat format: data is already array of field objects
                    fields = data
            else:
                # Wrapped format: {"data": [...]}
                fields = data.get("data", [])

            print(f"      ✓ Successfully fetched {len(fields)} fields from Portal 1")
            return fields
        else:
            print(f"      ✗ Error fetching fields: {response.get('error')}")
            return []

    def enrich_choice_fields_with_values(self, fields: List[Dict]) -> List[Dict]:
        """Fetch field details for choice fields to get choiceValues"""
        choice_field_types = ["SINGLE_SELECT", "MULTI_SELECT", "SINGLE_CHOICE", "MULTIPLE_CHOICE"]
        choice_fields_count = sum(1 for f in fields if f.get("fieldType") in choice_field_types)

        if choice_fields_count == 0:
            return fields

        print(f"\n   Enriching {choice_fields_count} choice fields with dropdown values...")

        enriched_count = 0
        api_base = self.portal1_config['api_base']
        headers = {"api-key": self.portal1_config['api_key']}

        for i, field in enumerate(fields):
            field_type = field.get("fieldType")

            # Only fetch details for choice fields that don't already have choiceValues
            if field_type in choice_field_types and not field.get("choiceValues"):
                field_id = field.get("fieldId")
                if not field_id:
                    continue

                # Fetch field details with options
                detail_endpoint = self.portal1_config['endpoints']['field_detail'].replace('{fieldId}', str(field_id))
                url = f"{api_base}{detail_endpoint}?includeFields=options"

                response = self._make_request("GET", url, headers)

                if response["success"] and response.get("data"):
                    detail = response["data"]

                    # NOTE: We do NOT update fieldType here because it can cause issues
                    # We keep the original fieldType from /api/v1/all-fields
                    # and just add the choiceValues for fields that have dropdown options

                    # API returns fieldOptions, need to transform to choiceValues format
                    if "fieldOptions" in detail and detail["fieldOptions"]:
                        # Transform fieldOptions to choiceValues format
                        # Preserve optionColor for fallback add-option endpoint
                        choice_values = []
                        for option in detail["fieldOptions"]:
                            choice_values.append({
                                "value": option.get("optionValue"),
                                "label": option.get("optionLabel"),
                                "color": option.get("optionColor", "GRAY")  # Preserve color
                            })
                        field["choiceValues"] = choice_values
                        enriched_count += 1
                    # Also check if choiceValues already exists (different API versions)
                    elif "choiceValues" in detail and detail["choiceValues"]:
                        field["choiceValues"] = detail["choiceValues"]
                        enriched_count += 1
                    else:
                        # API returned success but no options found
                        print(f"      ⚠ Field {field_id} ({field.get('fieldLabel', 'Unknown')}): No fieldOptions or choiceValues in response")
                else:
                    # API call failed - log the error for diagnosis
                    error_msg = response.get('error', 'Unknown error')
                    status_code = response.get('status_code', 'N/A')
                    print(f"      ✗ Field {field_id} ({field.get('fieldLabel', 'Unknown')}): API call failed - Status {status_code}: {error_msg}")
                    if response.get('response_body'):
                        print(f"         Response: {response['response_body']}")

                # Rate limiting
                if (i + 1) % 10 == 0:
                    time.sleep(self.rate_limits.get('field_detail_fetch', 0.1))

        print(f"      ✓ Enriched {enriched_count}/{choice_fields_count} choice fields with dropdown values")
        return fields

    def get_all_fields_from_portal2(self) -> List[Dict]:
        """Fetch all existing fields from Portal 2, following pagination"""
        print("\n   [2/5] Fetching existing fields from Portal 2...")

        base_url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['fields']}"
        headers = {"api-key": self.portal2_config['api_key']}

        all_fields = []
        url = base_url
        page = 1

        while url:
            response = self._make_request("GET", url, headers)
            if page == 1:
                self.log_operation("GET_ALL_FIELDS", "Portal 2", url, response)

            if not response["success"]:
                print(f"      ✗ Error fetching fields from Portal 2: {response.get('error')}")
                break

            data = response["data"]
            if isinstance(data, list):
                all_fields.extend(data)
                break  # no pagination in this format
            else:
                all_fields.extend(data.get("data", []))
                pagination = data.get("pagination", {})
                next_url = pagination.get("nextPage")
                url = next_url if next_url else None
                page += 1

        print(f"      ✓ Successfully fetched {len(all_fields)} existing fields from Portal 2")
        return all_fields

    def get_sections_from_portal1(self, object_types: List[str] = None) -> List[Dict]:
        """Fetch all field sections from Portal 1 for specified object types"""
        print("\n   Fetching field sections from Portal 1...")

        if not object_types:
            object_types = ["TASK", "PROJECT", "USER", "USERS", "COMPANY"]

        all_sections = []
        base_url = f"{self.portal1_config['v1_api_base']}{self.portal1_config['endpoints']['field_sections']}"
        headers = {
            "Content-Type": "application/json",
            "api-key": self.portal1_config['api_key']
        }

        for obj_type in object_types:
            # Skip USERS as it's handled by USER
            if obj_type == "USERS":
                continue

            url = f"{base_url}?fieldSectionType={obj_type}"
            response = self._make_request("GET", url, headers)
            self.log_operation("GET_SECTIONS", "Portal 1", url, response)

            if response["success"]:
                sections = response["data"] if isinstance(response["data"], list) else []
                all_sections.extend(sections)
            else:
                error_msg = response.get('error', 'Unknown error')
                status_code = response.get('status_code')
                if status_code != 400 and '400' not in str(error_msg):
                    print(f"      ⚠ Error fetching {obj_type} sections: {error_msg}")

        if all_sections:
            print(f"      ✓ Found {len(all_sections)} sections in Portal 1")
            return all_sections
        else:
            print(f"      ℹ No sections found (API may require different parameters)")
            return []

    def get_sections_from_portal2(self, object_types: List[str] = None) -> List[Dict]:
        """Fetch all field sections from Portal 2 for specified object types"""
        print("\n   Fetching field sections from Portal 2...")

        if not object_types:
            object_types = ["TASK", "PROJECT", "USER", "USERS", "COMPANY"]

        all_sections = []
        base_url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['field_sections']}"
        headers = {
            "Content-Type": "application/json",
            "api-key": self.portal2_config['api_key']
        }

        for obj_type in object_types:
            # Skip USERS as it's handled by USER
            if obj_type == "USERS":
                continue

            url = f"{base_url}?fieldSectionType={obj_type}"
            response = self._make_request("GET", url, headers)
            self.log_operation("GET_SECTIONS", "Portal 2", url, response)

            if response["success"]:
                sections = response["data"] if isinstance(response["data"], list) else []
                all_sections.extend(sections)
            else:
                error_msg = response.get('error', 'Unknown error')
                status_code = response.get('status_code')
                if status_code != 400 and '400' not in str(error_msg):
                    print(f"      ⚠ Error fetching {obj_type} sections: {error_msg}")

        if all_sections:
            print(f"      ✓ Found {len(all_sections)} sections in Portal 2")
            return all_sections
        else:
            print(f"      ℹ No sections found (API may require different parameters)")
            return []

    def create_section_in_portal2(self, section_name: str, object_type: str) -> Optional[Dict]:
        """Create a new field section in Portal 2"""
        url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['field_sections']}"
        headers = {
            "Content-Type": "application/json",
            "api-key": self.portal2_config['api_key']
        }

        # Correct field names based on API specification
        request_data = {
            "fieldSectionName": section_name,
            "fieldSectionType": object_type,
            "private": False
        }

        response = self._make_request("POST", url, headers, request_data)
        self.log_operation("CREATE_SECTION", "Portal 2", url, response, request_data=request_data)

        if response["success"]:
            created_section = response["data"]
            print(f"      ✓ Created section: {section_name} ({object_type})")
            return created_section
        else:
            print(f"      ✗ Failed to create section {section_name}: {response.get('error')}")
            return None

    def extract_sections_from_fields(self, fields: List[Dict], enabled_object_types: List[str] = None) -> List[Dict]:
        """Extract unique sections from field data (since GET /sections doesn't work)"""
        sections_map = {}
        section_counters = {}  # Track section count per object type for unique naming

        for field in fields:
            section_id = field.get("fieldSectionId")
            object_type = field.get("objectType")
            field_group = field.get("fieldGroup", "")

            # Filter by enabled object types if specified
            if enabled_object_types and object_type not in enabled_object_types:
                continue

            if section_id and object_type:
                key = (section_id, object_type)
                if key not in sections_map:
                    # Create meaningful unique section names
                    if field_group and field_group not in ["_default", ""]:
                        # Use fieldGroup as base name
                        section_name = f"{field_group}"
                    else:
                        # Track counter for this object type
                        if object_type not in section_counters:
                            section_counters[object_type] = 1
                            section_name = f"{object_type} Fields"
                        else:
                            section_counters[object_type] += 1
                            section_name = f"{object_type} Fields {section_counters[object_type]}"

                    sections_map[key] = {
                        "fieldSectionId": section_id,
                        "fieldSectionType": object_type,
                        "fieldSectionName": section_name,
                        "fieldGroup": field_group
                    }

        return list(sections_map.values())

    def map_and_create_sections(self, dry_run: bool = False) -> Dict[str, int]:
        """Map sections from Portal 1 to Portal 2, creating missing ones"""
        print("\n   Mapping field sections between portals...")

        # Get enabled object types from features
        features = self.migration_config.get('features', {})
        enabled_object_types = []
        if features.get('fields_task', True):
            enabled_object_types.append('TASK')
        if features.get('fields_project', True):
            enabled_object_types.append('PROJECT')
        if features.get('fields_user', True):
            enabled_object_types.extend(['USER', 'USERS'])
        if features.get('fields_company', True):
            enabled_object_types.append('COMPANY')

        # Try to fetch sections via API first with object type parameters
        portal1_sections = self.get_sections_from_portal1(enabled_object_types)
        portal2_sections = self.get_sections_from_portal2(enabled_object_types)

        # If API doesn't work, extract sections from fields
        if not portal1_sections and hasattr(self, '_portal1_all_fields'):
            print("\n      ℹ API didn't return sections, extracting from fields...")
            portal1_sections = self.extract_sections_from_fields(self._portal1_all_fields, enabled_object_types)
            print(f"      ✓ Extracted {len(portal1_sections)} unique sections from enabled object types")

        if not portal1_sections:
            print("\n      ℹ Section API unavailable - fields will use Portal 2's default sections")
            print("      ℹ To preserve Portal 1 section organization:")
            print("         1. Manually create sections in Portal 2 UI matching Portal 1")
            print("         2. Create section_mapping.json with Portal 1 ID → Portal 2 ID mappings")
            print("         3. Place file in the migration directory")
            print("      ℹ Fields will be organized by objectType (TASK, PROJECT, USER, COMPANY)")

            # Try to load manual section mapping if it exists
            if os.path.exists('section_mapping.json'):
                try:
                    with open('section_mapping.json', 'r') as f:
                        manual_mapping = json.load(f)
                        if 'mappings' in manual_mapping:
                            self.section_mapping = manual_mapping['mappings']
                            print(f"\n      ✓ Loaded manual section mapping ({len(self.section_mapping)} mappings)")
                            return self.section_mapping
                except Exception as e:
                    print(f"      ⚠ Error loading manual section mapping: {e}")

            return {}

        # Create lookup map for Portal 2 sections by (sectionName, objectType)
        # Also build a Portal 2 section_id → private flag map so fields can match section privacy
        portal2_section_map = {}
        p2_section_private_map = {}
        for section in portal2_sections:
            # Handle different possible field names (API uses fieldSectionName and fieldSectionType)
            section_name = section.get("fieldSectionName") or section.get("sectionName") or section.get("name")
            object_type = section.get("fieldSectionType") or section.get("objectType")
            section_id = section.get("fieldSectionId") or section.get("sectionId") or section.get("id")
            is_private = section.get("private", False) or section.get("isPrivate", False)

            if section_name and object_type:
                key = (section_name, object_type)
                portal2_section_map[key] = section_id
            if section_id is not None:
                p2_section_private_map[str(section_id)] = is_private

        # Stash the privacy map on self so create_field_in_portal2 can read it
        self.p2_section_private_map = p2_section_private_map

        # Map Portal 1 sections to Portal 2
        section_mapping = {}
        sections_created = 0
        sections_mapped = 0

        for p1_section in portal1_sections:
            p1_section_name = p1_section.get("fieldSectionName") or p1_section.get("sectionName") or p1_section.get("name")
            p1_object_type = p1_section.get("fieldSectionType") or p1_section.get("objectType")
            p1_section_id = p1_section.get("fieldSectionId") or p1_section.get("sectionId") or p1_section.get("id")

            if not p1_section_name or not p1_object_type or not p1_section_id:
                continue

            key = (p1_section_name, p1_object_type)

            if key in portal2_section_map:
                # Section already exists in Portal 2
                p2_section_id = portal2_section_map[key]
                section_mapping[str(p1_section_id)] = p2_section_id
                sections_mapped += 1
                if dry_run:
                    print(f"      ✓ Mapped: {p1_section_name} ({p1_object_type}) - P1:{p1_section_id} → P2:{p2_section_id}")
            else:
                # Section doesn't exist - create it
                if not dry_run:
                    created_section = self.create_section_in_portal2(p1_section_name, p1_object_type)
                    if created_section:
                        p2_section_id = created_section.get("sectionId") or created_section.get("fieldSectionId") or created_section.get("id")
                        section_mapping[str(p1_section_id)] = p2_section_id
                        sections_created += 1
                        # Remember created sections by name so the cloned-items
                        # report can distinguish them from pre-existing matches
                        self.created_sections.append({
                            "fieldSectionName": p1_section_name,
                            "fieldSectionType": p1_object_type,
                            "portal1_id": p1_section_id,
                            "portal2_id": p2_section_id
                        })
                else:
                    print(f"      [DRY RUN] Would create: {p1_section_name} ({p1_object_type}) - P1:{p1_section_id}")

        print(f"\n      ✓ Mapped {sections_mapped} existing sections")
        if not dry_run:
            print(f"      ✓ Created {sections_created} new sections")
        else:
            print(f"      [DRY RUN] Would create {len(portal1_sections) - sections_mapped} new sections")

        # Store mapping
        self.section_mapping = section_mapping

        return section_mapping

    def map_existing_fields(self, portal1_fields: List[Dict], portal2_fields: List[Dict]) -> tuple:
        """Map existing fields from Portal 2 and identify fields to create"""
        print("\n   [3/5] Mapping existing fields and identifying new fields...")

        # Create a lookup map for Portal 2 fields by (fieldLabel, objectType)
        portal2_field_map = {}
        for field in portal2_fields:
            key = (field.get("fieldLabel"), field.get("objectType"))
            portal2_field_map[key] = field

        # Map existing fields and identify new ones
        mapped_count = 0
        new_fields = []

        for p1_field in portal1_fields:
            key = (p1_field.get("fieldLabel"), p1_field.get("objectType"))

            if key in portal2_field_map:
                # Field already exists in Portal 2 - create mapping
                p2_field = portal2_field_map[key]
                self.field_mapping[str(p1_field["fieldId"])] = {
                    "portal1_id": p1_field["fieldId"],
                    "portal2_id": p2_field.get("fieldId"),
                    "fieldLabel": p1_field["fieldLabel"],
                    "objectType": p1_field["objectType"],
                    "matched": True
                }
                mapped_count += 1
            else:
                # Field doesn't exist in Portal 2 - needs to be created
                new_fields.append(p1_field)

        print(f"      ✓ Mapped {mapped_count} existing fields")
        print(f"      ✓ Identified {len(new_fields)} new fields to create")

        return new_fields, mapped_count

    def filter_fields_for_migration(self, all_fields: List[Dict]) -> List[Dict]:
        """Filter fields that should be migrated"""
        print("\n   [4/5] Filtering fields for migration...")

        # Check which object types are enabled via feature flags
        features = self.migration_config.get('features', {})
        enabled_object_types = []

        if features.get('fields_task', True):
            enabled_object_types.append('TASK')
        if features.get('fields_project', True):
            enabled_object_types.append('PROJECT')
        if features.get('fields_user', True):
            enabled_object_types.extend(['USER', 'USERS'])  # Handle both USER and USERS
        if features.get('fields_company', True):
            enabled_object_types.append('COMPANY')

        # If no object types are enabled, use default
        if not enabled_object_types:
            enabled_object_types = ["TASK", "PROJECT", "USER", "USERS", "COMPANY"]

        excluded_ids = self.migration_config.get('excluded_field_ids', [])

        filtered_fields = []
        object_type_counts = {}

        for field in all_fields:
            obj_type = field.get("objectType")

            # Include only enabled object types
            if obj_type not in enabled_object_types:
                continue

            # Exclude specific field IDs
            if str(field.get("fieldId")) in excluded_ids:
                continue

            # Exclude system fields (they already exist in destination)
            if field.get("isSystem", False):
                continue

            # Exclude Gantt/computed fields — KEY_EVENTS and INTERVALS (from all-fields)
            # and fields with no fieldType (same fields via /api/1.0/fields) cannot be
            # created via the field creation API (returns 400)
            if field.get("fieldType") in ["KEY_EVENTS", "INTERVALS", None, ""]:
                continue

            filtered_fields.append(field)

            # Count by object type for reporting
            object_type_counts[obj_type] = object_type_counts.get(obj_type, 0) + 1

        # Show breakdown by object type
        print(f"      ✓ Filtered to {len(filtered_fields)} fields:")
        for obj_type, count in sorted(object_type_counts.items()):
            print(f"         - {obj_type}: {count} fields")

        return filtered_fields

    def create_field_in_portal2(self, field: Dict) -> Optional[Dict]:
        """Create a field in Portal 2"""
        url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['fields']}"
        headers = {"api-key": self.portal2_config['api_key']}

        # Validate required fields
        if not field.get("fieldLabel"):
            print(f"      ✗ Skipping field: Missing fieldLabel")
            return None

        if not field.get("fieldType"):
            print(f"      ✗ Skipping field {field.get('fieldLabel')}: Missing fieldType")
            return None

        # Prepare field data (remove Portal 1 specific IDs)
        field_type = field.get("fieldType")

        # FIELD TYPE NORMALIZATION
        # Portal 1's /api/v1/all-fields returns: SINGLE_SELECT, MULTI_SELECT
        # Portal 1's /api/1.0/fields/{id} returns: SINGLE_CHOICE, MULTIPLE_CHOICE, TEXT, NUMBER, etc.
        # Portal 2's /api/1.0/fields expects: SINGLE_CHOICE, MULTIPLE_CHOICE, TEXT, NUMBER, etc.
        #
        # SPECIAL CASE: Portal 1 sometimes returns fieldType=SINGLE_SELECT with no choiceValues
        # In this case, the ACTUAL type is in fieldDataType (TEXT, NUMBER, DATE, USER, etc.)
        # This happens especially with PROJECT fields that are lookups, formulas, or special fields
        if field_type in ["SINGLE_SELECT", "MULTI_SELECT"]:
            has_choice_values = bool(field.get("choiceValues"))
            if not has_choice_values and "fieldDataType" in field:
                # Use fieldDataType as the actual field type
                # Portal 1's fieldDataType → Portal 2's fieldType mapping
                actual_type = field.get("fieldDataType")

                # Map fieldDataType to Portal 2 field types
                field_data_type_mapping = {
                    "USER": "SINGLE_USER",      # Portal 2 expects SINGLE_USER, not USER
                    "USERS": "MULTIPLE_USER",   # Portal 2 expects MULTIPLE_USER for multi-user fields
                    "BOOLEAN": "YES_OR_NO",     # Portal 2 expects YES_OR_NO, not BOOLEAN
                    "TEXT": "TEXT",
                    "NUMBER": "NUMBER",
                    "DATE": "DATE",
                    "DATETIME": "DATE_TIME",
                    "MULTI_LINE_TEXT": "MULTI_LINE_TEXT"
                }

                normalized_field_type = field_data_type_mapping.get(actual_type, actual_type)
                # Using fieldDataType instead of SINGLE_SELECT for fields without options
            else:
                # Has choice values, so normalize to SINGLE_CHOICE/MULTIPLE_CHOICE
                field_type_mapping = {
                    "SINGLE_SELECT": "SINGLE_CHOICE",
                    "MULTI_SELECT": "MULTIPLE_CHOICE"
                }
                normalized_field_type = field_type_mapping.get(field_type, field_type)
        else:
            # Not a SELECT type, use as-is
            normalized_field_type = field_type

        request_data = {
            "fieldLabel": field.get("fieldLabel"),
            "fieldType": normalized_field_type,
            "objectType": field.get("objectType"),
            "private": field.get("private", False),
            "enabled": field.get("enabled", True)
        }

        # Add REQUIRED fields that were missing (causing 500 errors)
        # fieldDataType is required for SINGLE_SELECT, MULTI_SELECT fields
        if "fieldDataType" in field:
            request_data["fieldDataType"] = field["fieldDataType"]

        # fieldName is the internal API field name
        if "fieldName" in field:
            request_data["fieldName"] = field["fieldName"]

        # description is required (can be empty string)
        request_data["description"] = field.get("description", "")

        # AUTOMATIC SECTION MAPPING
        # Map Portal 1 section ID to Portal 2 section ID using name-based mapping
        # This preserves section organization from Portal 1
        if "fieldSectionId" in field and field["fieldSectionId"]:
            p1_section_id = str(field["fieldSectionId"])
            if p1_section_id in self.section_mapping:
                # Use mapped section ID from Portal 2
                p2_section_id = self.section_mapping[p1_section_id]
                request_data["fieldSectionId"] = p2_section_id

                # If the destination section is private, the field MUST also be private=true
                # Rocketlane rejects "Field of Private section can't be private=false"
                p2_priv_map = getattr(self, "p2_section_private_map", {})
                if p2_priv_map.get(str(p2_section_id), False):
                    request_data["private"] = True
            # If no mapping exists, Portal 2 will auto-assign to default section

        # Add fieldGroup if present (helps organize fields within sections)
        if "fieldGroup" in field and field["fieldGroup"]:
            request_data["fieldGroup"] = field["fieldGroup"]

        # Add description if present (legacy field name)
        if "fieldDescription" in field and field["fieldDescription"]:
            request_data["fieldDescription"] = field["fieldDescription"]

        # RATING fields require ratingScale parameter
        if normalized_field_type == "RATING":
            # Portal 2 requires ratingScale: "THREE", "FIVE", "TEN", etc.
            if "ratingScale" in field:
                request_data["ratingScale"] = field["ratingScale"]
            else:
                # Default to THREE if not specified
                request_data["ratingScale"] = "THREE"

        # Add choice values for choice fields only
        # Portal 2's /api/1.0/fields expects fieldOptions with structure:
        # [{"optionLabel": "High", "optionColor": "RED"}]
        # NOT choiceValues with [{"value": "...", "label": "...", "color": "..."}]
        # NOTE: NUMBER fields with options are NOT supported - they'll be created as plain NUMBER fields
        if field_type in ["SINGLE_SELECT", "MULTI_SELECT", "SINGLE_CHOICE", "MULTIPLE_CHOICE"]:
            if "choiceValues" in field and field["choiceValues"]:
                # Transform choiceValues to fieldOptions format
                field_options = []
                for choice in field["choiceValues"]:
                    field_options.append({
                        "optionLabel": choice.get("label", choice.get("optionLabel", "")),
                        "optionColor": choice.get("color", choice.get("optionColor", "GRAY"))
                    })
                request_data["fieldOptions"] = field_options

        # STEP 1: Try creating field with choiceValues (primary approach)
        response = self._make_request("POST", url, headers, request_data)
        self.log_operation("CREATE_FIELD", "Portal 2", url, response,
                           request_data=request_data,
                           resource_id=field.get("fieldId"),
                           resource_name=field.get("fieldLabel"))

        if response["success"]:
            created_field = response["data"]

            # Store mapping
            self.field_mapping[str(field["fieldId"])] = {
                "portal1_id": field["fieldId"],
                "portal2_id": created_field.get("fieldId"),
                "fieldLabel": field["fieldLabel"],
                "objectType": field["objectType"]
            }

            # STEP 2: Fallback - Check if choice field was created without options
            # If optionsAvailable is False, use add-option endpoint as fallback
            is_choice_field = field_type in ["SINGLE_SELECT", "MULTI_SELECT", "SINGLE_CHOICE", "MULTIPLE_CHOICE"]
            has_choice_values = "choiceValues" in field and field["choiceValues"]
            options_available = created_field.get("optionsAvailable", True)

            if is_choice_field and has_choice_values and not options_available:
                print(f"         ⚠ Choice values not added during creation, using fallback...")

                # Use two-step approach: add options individually
                success = self.add_field_options(created_field.get("fieldId"), field["choiceValues"])

                if success:
                    print(f"      ✓ {field['fieldLabel']} ({field['objectType']}) [fallback used]")
                else:
                    print(f"      ⚠ {field['fieldLabel']} ({field['objectType']}) - field created but options failed")
            else:
                print(f"      ✓ {field['fieldLabel']} ({field['objectType']})")

            return created_field
        else:
            status_code = response.get('status_code', 'N/A')
            print(f"      ✗ {field['fieldLabel']} ({status_code})")
            return None

    def add_field_options(self, field_id: int, choice_values: List[Dict]) -> bool:
        """
        Add options to an existing field using the add-option endpoint (two-step fallback).

        This is a fallback approach when creating a field with choiceValues doesn't work.
        Uses POST /api/1.0/fields/{fieldId}/add-option to add each option individually.

        Args:
            field_id: The ID of the field to add options to
            choice_values: List of choice value dictionaries with 'label' and 'value'

        Returns:
            bool: True if all options were added successfully, False otherwise
        """
        if not choice_values:
            return True

        api_base = self.portal2_config['api_base']
        headers = {"api-key": self.portal2_config['api_key'], "Content-Type": "application/json"}

        success_count = 0
        failed_count = 0

        for choice in choice_values:
            # Construct add-option endpoint URL
            # Using /api/1.0/fields/{fieldId}/add-option as per API documentation
            url = f"{api_base}/api/1.0/fields/{field_id}/add-option"

            # Prepare option data (API expects optionLabel and optionColor)
            option_data = {
                "optionLabel": choice.get("label", ""),
                "optionColor": choice.get("color", "GRAY")
            }

            try:
                response = self._make_request("POST", url, headers, option_data)

                if response["success"]:
                    success_count += 1
                else:
                    failed_count += 1
                    error_msg = response.get('error', 'Unknown error')
                    print(f"            ✗ Failed to add option '{option_data['optionLabel']}': {error_msg}")

                # Rate limiting between option additions
                time.sleep(self.rate_limits.get('field_option_add', 0.1))

            except Exception as e:
                failed_count += 1
                print(f"            ✗ Exception adding option '{option_data['optionLabel']}': {str(e)}")

        # Log summary
        total = len(choice_values)
        if failed_count > 0:
            print(f"         Options: {success_count}/{total} added ({failed_count} failed)")
        else:
            print(f"         Options: {success_count}/{total} added successfully")

        # Return True only if all options were added successfully
        return failed_count == 0

    def migrate_fields(self, dry_run: bool = False):
        """Migrate all fields from Portal 1 to Portal 2"""
        print("\n" + "=" * 80)
        print("STEP 1: FIELDS MIGRATION (PROJECT, TASK, USER, COMPANY)")
        print("=" * 80)

        # Get fields from both portals
        portal1_fields = self.get_all_fields_from_portal1()
        if not portal1_fields:
            print("   ⚠ No fields found in Portal 1")
            return

        # Cache ALL fields for skills migration to use (before filtering)
        self._portal1_all_fields = portal1_fields

        # OPTIMIZATION: Filter to target object types BEFORE enrichment
        # This significantly speeds up enrichment by only processing relevant fields
        print("\n   [4/5] Filtering fields for migration...")
        filtered_fields = self.filter_fields_for_migration(portal1_fields)
        if not filtered_fields:
            print("   ⚠ No fields left after filtering")
            return

        # Enrich ONLY the filtered fields (not all 989 fields)
        # This makes enrichment much faster
        if not dry_run:
            filtered_fields = self.enrich_choice_fields_with_values(filtered_fields)
        else:
            print("\n   ⏩ Skipping choice field enrichment in dry run mode (for performance)")
            print("      Note: Choice field dropdown values will be fetched during actual migration")

        portal2_fields = self.get_all_fields_from_portal2()

        # Cache fields for skills migration to use
        self._portal2_all_fields = portal2_fields

        # Map and create sections before creating fields
        self.map_and_create_sections(dry_run=dry_run)

        # Fields are already filtered above
        # filtered_fields is ready to use
        if not filtered_fields:
            print("   ⚠ No fields left after filtering")
            return

        # Map existing fields and identify new fields to create
        new_fields, mapped_count = self.map_existing_fields(filtered_fields, portal2_fields)

        if dry_run:
            print(f"\n   [5/5] DRY RUN - Skipping field creation")
            print(f"      Would map {mapped_count} existing fields")
            print(f"      Would create {len(new_fields)} new fields in Portal 2")
            return

        # Create only new fields
        if len(new_fields) == 0:
            print(f"\n   [5/5] All fields already exist in Portal 2 (0 new fields to create)")
            print(f"      ✓ Mapped {mapped_count} existing fields")
        else:
            print(f"\n   [5/5] Creating {len(new_fields)} new fields in Portal 2...")
            success_count = 0
            for field in new_fields:
                if self.create_field_in_portal2(field):
                    success_count += 1
                time.sleep(self.rate_limits.get('field_creation', 0.2))

            print(f"\n      ✓ Mapped {mapped_count} existing fields")
            print(f"      ✓ Successfully created {success_count}/{len(new_fields)} new fields")

            # Show warning if all new fields failed
            if success_count == 0 and len(new_fields) > 0:
                print(f"\n      ⚠ WARNING: All new fields failed to create!")
                print(f"         Check migration_log.json for detailed error information")

    # ==================== ROLES MIGRATION ====================

    def get_roles_from_portal1(self) -> List[Dict]:
        """Fetch all roles from Portal 1"""
        print("\n   [1/4] Fetching roles from Portal 1...")

        url = f"{self.portal1_config['v1_api_base']}{self.portal1_config['endpoints']['roles']}"
        headers = {"api-key": self.portal1_config['api_key']}

        response = self._make_request("GET", url, headers)
        self.log_operation("GET_ROLES", "Portal 1", url, response)

        if response["success"]:
            roles = response["data"] if isinstance(response["data"], list) else response["data"].get("data", [])
            print(f"      ✓ Fetched {len(roles)} roles from Portal 1")
            return roles
        else:
            print(f"      ✗ Error fetching roles: {response.get('error')}")
            return []

    def get_roles_from_portal2(self) -> List[Dict]:
        """Fetch all existing roles from Portal 2"""
        print("\n   [2/4] Fetching existing roles from Portal 2...")

        url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['roles']}"
        headers = {"api-key": self.portal2_config['api_key']}

        response = self._make_request("GET", url, headers)
        self.log_operation("GET_ROLES", "Portal 2", url, response)

        if response["success"]:
            roles = response["data"] if isinstance(response["data"], list) else response["data"].get("data", [])
            print(f"      ✓ Fetched {len(roles)} existing roles from Portal 2")
            return roles
        else:
            print(f"      ✗ Error fetching roles from Portal 2: {response.get('error')}")
            return []

    def map_existing_roles(self, portal1_roles: List[Dict], portal2_roles: List[Dict]) -> tuple:
        """Map existing roles from Portal 2 and identify roles to create"""
        print("\n   [3/4] Mapping existing roles and identifying new roles...")

        # Create a lookup map for Portal 2 roles by roleName
        portal2_role_map = {}
        for role in portal2_roles:
            role_name = role.get("roleName")
            if role_name:
                portal2_role_map[role_name] = role

        # Map existing roles and identify new ones
        mapped_count = 0
        new_roles = []

        for p1_role in portal1_roles:
            role_name = p1_role.get("roleName")

            if role_name in portal2_role_map:
                # Role already exists in Portal 2 - create mapping
                p2_role = portal2_role_map[role_name]
                self.role_mapping[str(p1_role.get("roleId", role_name))] = {
                    "portal1_id": p1_role.get("roleId"),
                    "portal2_id": p2_role.get("roleId"),
                    "roleName": role_name,
                    "matched": True
                }
                mapped_count += 1
            else:
                # Role doesn't exist in Portal 2 - needs to be created
                new_roles.append(p1_role)

        print(f"      ✓ Mapped {mapped_count} existing roles")
        print(f"      ✓ Identified {len(new_roles)} new roles to create")

        return new_roles, mapped_count

    def create_role_in_portal2(self, role: Dict) -> Optional[Dict]:
        """Create a role in Portal 2"""
        url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['roles']}"
        headers = {"api-key": self.portal2_config['api_key']}

        # Validate required fields
        if not role.get("roleName"):
            print(f"      ✗ Skipping role: Missing roleName")
            return None

        request_data = {
            "roleName": role.get("roleName"),
            "roleDescription": role.get("roleDescription", "")
        }

        response = self._make_request("POST", url, headers, request_data)
        self.log_operation("CREATE_ROLE", "Portal 2", url, response, request_data=request_data)

        if response["success"]:
            created_role = response["data"]

            # Store mapping
            self.role_mapping[str(role.get("roleId", role.get("roleName")))] = {
                "portal1_id": role.get("roleId"),
                "portal2_id": created_role.get("roleId"),
                "roleName": role.get("roleName")
            }

            print(f"      ✓ {role.get('roleName')}")
            return created_role
        else:
            status_code = response.get('status_code', 'N/A')
            print(f"      ✗ {role.get('roleName')} ({status_code})")
            return None

    def migrate_roles(self, dry_run: bool = False):
        """Migrate all roles"""
        print("\n" + "=" * 80)
        print("STEP 2: ROLES MIGRATION")
        print("=" * 80)

        # Get roles from both portals
        portal1_roles = self.get_roles_from_portal1()
        if not portal1_roles:
            print("   ⚠ No roles found in Portal 1")
            return

        portal2_roles = self.get_roles_from_portal2()

        # Map existing roles and identify new roles to create
        new_roles, mapped_count = self.map_existing_roles(portal1_roles, portal2_roles)

        if dry_run:
            print(f"\n   [4/4] DRY RUN - Skipping role creation")
            print(f"      Would map {mapped_count} existing roles")
            print(f"      Would create {len(new_roles)} new roles in Portal 2")
            return

        # Create only new roles
        if len(new_roles) == 0:
            print(f"\n   [4/4] All roles already exist in Portal 2 (0 new roles to create)")
            print(f"      ✓ Mapped {mapped_count} existing roles")
        else:
            print(f"\n   [4/4] Creating {len(new_roles)} new roles in Portal 2...")
            success_count = 0
            for role in new_roles:
                if self.create_role_in_portal2(role):
                    success_count += 1
                time.sleep(self.rate_limits.get('role_creation', 0.2))

            print(f"\n      ✓ Mapped {mapped_count} existing roles")
            print(f"      ✓ Successfully created {success_count}/{len(new_roles)} new roles")

            # Show warning if all new roles failed
            if success_count == 0 and len(new_roles) > 0:
                print(f"\n      ⚠ WARNING: All new roles failed to create!")
                print(f"         Some role names may be reserved or require special permissions")
                print(f"         Check migration_log.json for detailed error information")

    # ==================== SKILLS MIGRATION ====================

    def get_skills_from_portal1(self) -> List[Dict]:
        """Fetch all skills from Portal 1 using skills endpoint"""
        print("\n   [1/4] Fetching skills from Portal 1...")

        # Use the dedicated skills endpoint
        url = f"{self.portal1_config['v1_api_base']}{self.portal1_config['endpoints']['skills']}"
        headers = {"api-key": self.portal1_config['api_key']}

        response = self._make_request("GET", url, headers)
        self.log_operation("GET_SKILLS", "Portal 1", url, response)

        if not response["success"]:
            print(f"      ✗ Error fetching skills: {response.get('error')}")
            return []

        # Handle different response formats dynamically (similar to fields fix)
        data = response["data"]

        if isinstance(data, list):
            # Case A: Endpoint returns raw integer IDs — fetch each field detail
            if data and isinstance(data[0], (int, str)) and not isinstance(data[0], dict):
                skills = []
                fields_endpoint = self.portal1_config['endpoints'].get('field_detail', '/api/1.0/fields/{fieldId}')
                for skill_id in data:
                    detail_url = f"{self.portal1_config['api_base']}{fields_endpoint.replace('{fieldId}', str(skill_id))}"
                    detail_resp = self._make_request("GET", detail_url, headers)
                    if detail_resp["success"] and detail_resp.get("data"):
                        skills.append(detail_resp["data"])
            # Case B: Nested format {objectType, fields[]}
            elif data and isinstance(data[0], dict) and "fields" in data[0] and not data[0].get("fieldId"):
                skills = []
                for item in data:
                    if isinstance(item.get("fields"), list):
                        skills.extend(item["fields"])
            # Case C: Flat list of skill objects
            else:
                skills = data
        else:
            # Wrapped format: {"data": [...]}
            skills = data.get("data", [])

        # The /skill/fields endpoint already filters to skill-tagged fields,
        # so trust its output rather than re-filtering by fieldType=SKILL
        # (actual fieldType varies — SINGLE_CHOICE, YES_OR_NO, etc.)
        skills = [s for s in skills if isinstance(s, dict) and s.get("fieldLabel")]

        print(f"      ✓ Fetched {len(skills)} skills from Portal 1")
        return skills

    def get_skills_from_portal2(self) -> List[Dict]:
        """Fetch all existing skills from Portal 2"""
        print("\n   [2/4] Fetching existing skills from Portal 2...")

        # Skills are stored as fields with fieldType="SKILL"
        if not hasattr(self, '_portal2_all_fields') or not self._portal2_all_fields:
            url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['fields']}"
            headers = {"api-key": self.portal2_config['api_key']}
            response = self._make_request("GET", url, headers)

            if not response["success"]:
                print(f"      ✗ Error fetching fields from Portal 2: {response.get('error')}")
                return []

            all_fields = response["data"].get("data", [])
        else:
            all_fields = self._portal2_all_fields

        # Filter for skills
        skills = [
            field for field in all_fields
            if field.get("fieldType") == "SKILL" and field.get("objectType") == "USER"
        ]

        print(f"      ✓ Fetched {len(skills)} existing skills from Portal 2")
        return skills

    def map_existing_skills(self, portal1_skills: List[Dict], portal2_skills: List[Dict]) -> tuple:
        """Map existing skills from Portal 2 and identify skills to create"""
        print("\n   [3/4] Mapping existing skills and identifying new skills...")

        # Create a lookup map for Portal 2 skills by fieldLabel
        portal2_skill_map = {}
        for skill in portal2_skills:
            skill_label = skill.get("fieldLabel")
            if skill_label:
                portal2_skill_map[skill_label] = skill

        # Map existing skills and identify new ones
        mapped_count = 0
        new_skills = []

        for p1_skill in portal1_skills:
            skill_label = p1_skill.get("fieldLabel")

            if skill_label in portal2_skill_map:
                # Skill already exists in Portal 2 - create mapping
                p2_skill = portal2_skill_map[skill_label]
                self.skill_mapping[str(p1_skill.get("fieldId", skill_label))] = {
                    "portal1_id": p1_skill.get("fieldId"),
                    "portal2_id": p2_skill.get("fieldId"),
                    "fieldLabel": skill_label,
                    "matched": True
                }
                mapped_count += 1
            else:
                # Skill doesn't exist in Portal 2 - needs to be created
                new_skills.append(p1_skill)

        print(f"      ✓ Mapped {mapped_count} existing skills")
        print(f"      ✓ Identified {len(new_skills)} new skills to create")

        return new_skills, mapped_count

    def create_skill_in_portal2(self, skill: Dict) -> Optional[Dict]:
        """Create a skill in Portal 2 (skills are created as fields)"""
        url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['fields']}"
        headers = {"api-key": self.portal2_config['api_key']}

        # Validate required fields
        if not skill.get("fieldLabel"):
            print(f"      ✗ Skipping skill: Missing fieldLabel")
            return None

        # Preserve the actual fieldType (skills can be SINGLE_CHOICE, YES_OR_NO, etc.)
        # The /api/v1/skill/fields endpoint identifies them as skills regardless of underlying type
        actual_field_type = skill.get("fieldType") or "SKILL"

        request_data = {
            "fieldLabel": skill.get("fieldLabel"),
            "fieldType": actual_field_type,
            "objectType": skill.get("objectType", "USER"),
            "private": skill.get("private", False),
            "enabled": skill.get("enabled", True)
        }

        # Add description if present
        if "fieldDescription" in skill and skill["fieldDescription"]:
            request_data["fieldDescription"] = skill["fieldDescription"]

        # Preserve choice values for SINGLE_CHOICE/MULTIPLE_CHOICE skills
        if actual_field_type in ["SINGLE_CHOICE", "MULTIPLE_CHOICE", "SINGLE_SELECT", "MULTI_SELECT"]:
            if "fieldOptions" in skill and skill["fieldOptions"]:
                request_data["fieldOptions"] = skill["fieldOptions"]
            elif "choiceValues" in skill and skill["choiceValues"]:
                # Transform choiceValues to fieldOptions format
                field_options = []
                for choice in skill["choiceValues"]:
                    field_options.append({
                        "optionLabel": choice.get("label", choice.get("optionLabel", "")),
                        "optionColor": choice.get("color", choice.get("optionColor", "GRAY"))
                    })
                request_data["fieldOptions"] = field_options

        response = self._make_request("POST", url, headers, request_data)
        self.log_operation("CREATE_SKILL", "Portal 2", url, response,
                           request_data=request_data,
                           resource_id=skill.get("fieldId"),
                           resource_name=skill.get("fieldLabel"))

        if response["success"]:
            created_skill = response["data"]

            # Store mapping
            self.skill_mapping[str(skill.get("fieldId", skill.get("fieldLabel")))] = {
                "portal1_id": skill.get("fieldId"),
                "portal2_id": created_skill.get("fieldId"),
                "fieldLabel": skill.get("fieldLabel")
            }

            print(f"      ✓ {skill.get('fieldLabel')}")
            return created_skill
        else:
            status_code = response.get('status_code', 'N/A')
            print(f"      ✗ {skill.get('fieldLabel')} ({status_code})")
            return None

    def migrate_skills(self, dry_run: bool = False):
        """Migrate all skills"""
        print("\n" + "=" * 80)
        print("STEP 3: SKILLS MIGRATION")
        print("=" * 80)

        # Get skills from both portals
        portal1_skills = self.get_skills_from_portal1()
        if not portal1_skills:
            print("   ⚠ No skills found in Portal 1")
            return

        portal2_skills = self.get_skills_from_portal2()

        # Map existing skills and identify new skills to create
        new_skills, mapped_count = self.map_existing_skills(portal1_skills, portal2_skills)

        if dry_run:
            print(f"\n   [4/4] DRY RUN - Skipping skill creation")
            print(f"      Would map {mapped_count} existing skills")
            print(f"      Would create {len(new_skills)} new skills in Portal 2")
            return

        # Create only new skills
        if len(new_skills) == 0:
            print(f"\n   [4/4] All skills already exist in Portal 2 (0 new skills to create)")
            print(f"      ✓ Mapped {mapped_count} existing skills")
        else:
            print(f"\n   [4/4] Creating {len(new_skills)} new skills in Portal 2...")
            success_count = 0
            for skill in new_skills:
                if self.create_skill_in_portal2(skill):
                    success_count += 1
                time.sleep(self.rate_limits.get('skill_creation', 0.2))

            print(f"\n      ✓ Mapped {mapped_count} existing skills")
            print(f"      ✓ Successfully created {success_count}/{len(new_skills)} new skills")

            # Show warning if all new skills failed
            if success_count == 0 and len(new_skills) > 0:
                print(f"\n      ⚠ WARNING: All new skills failed to create!")
                print(f"         Check migration_log.json for detailed error information")

    # ==================== USERS MIGRATION ====================

    def get_users_from_portal1(self) -> List[Dict]:
        """Fetch all users from Portal 1"""
        print("\n   [1/2] Fetching users from Portal 1...")

        url = f"{self.portal1_config['api_base']}{self.portal1_config['endpoints']['users']}"
        headers = {"api-key": self.portal1_config['api_key']}

        response = self._make_request("GET", url, headers)
        self.log_operation("GET_USERS", "Portal 1", url, response)

        if response["success"]:
            users = response["data"].get("data", [])
            print(f"      ✓ Fetched {len(users)} users from Portal 1")
            return users
        else:
            print(f"      ✗ Error fetching users: {response.get('error')}")
            return []

    def create_user_in_portal2(self, user: Dict) -> Optional[Dict]:
        """Create a user in Portal 2"""
        url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['users']}"
        headers = {"api-key": self.portal2_config['api_key']}

        # Handle both 'email' and 'emailId' field names
        email = user.get("email") or user.get("emailId")
        if not email:
            print(f"      ✗ Skipping user: Missing email")
            return None

        request_data = {
            "emailId": email,
            "userName": user.get("userName", email.split('@')[0]),
            "firstName": user.get("firstName", ""),
            "lastName": user.get("lastName", ""),
            "userType": user.get("userType", "USER")
        }

        response = self._make_request("POST", url, headers, request_data)
        self.log_operation("CREATE_USER", "Portal 2", url, response, request_data=request_data)

        if response["success"]:
            created_user = response["data"]

            # Store mapping
            user_id = user.get("userId") or user.get("id")
            self.user_mapping[str(user_id)] = {
                "portal1_id": user_id,
                "portal2_id": created_user.get("userId"),
                "emailId": email
            }

            print(f"      ✓ {email}")
            return created_user
        else:
            status_code = response.get('status_code', 'N/A')
            print(f"      ✗ {email} ({status_code})")
            return None

    def filter_users_for_migration(self, all_users: List[Dict]) -> List[Dict]:
        """Filter users - only ACTIVE TEAM_MEMBER users"""
        print("\n   [2/3] Filtering users for migration...")

        filtered_users = []
        for user in all_users:
            user_status = user.get("status", "").upper()
            user_type = user.get("type", "").upper()

            # Only include ACTIVE TEAM_MEMBER users
            if user_status == "ACTIVE" and user_type == "TEAM_MEMBER":
                filtered_users.append(user)

        print(f"      ✓ Found {len(all_users)} total users")
        print(f"      ✓ Filtered to {len(filtered_users)} ACTIVE TEAM_MEMBER users")

        # Show which users will be migrated
        if filtered_users:
            print(f"\n      Users to be migrated:")
            for i, user in enumerate(filtered_users, 1):
                email = user.get('email', user.get('emailId', 'N/A'))
                name = f"{user.get('firstName', '')} {user.get('lastName', '')}".strip() or 'N/A'
                print(f"         {i}. {email} - {name}")

        return filtered_users

    def migrate_users(self, dry_run: bool = False):
        """Migrate all users (only ACTIVE TEAM_MEMBER users)"""
        print("\n" + "=" * 80)
        print("STEP 4: USERS MIGRATION (ACTIVE TEAM_MEMBER only)")
        print("=" * 80)

        all_users = self.get_users_from_portal1()
        if not all_users:
            print("   ⚠ No users found")
            return

        # Filter for ACTIVE TEAM_MEMBER users only
        users = self.filter_users_for_migration(all_users)
        if not users:
            print("   ⚠ No ACTIVE TEAM_MEMBER users to migrate")
            return

        if dry_run:
            print(f"\n   [3/3] DRY RUN - Would create {len(users)} ACTIVE TEAM_MEMBER users")
            return

        print(f"\n   [3/3] Creating {len(users)} ACTIVE TEAM_MEMBER users in Portal 2...")
        success_count = 0
        for user in users:
            if self.create_user_in_portal2(user):
                success_count += 1
            time.sleep(self.rate_limits.get('user_creation', 0.3))

        print(f"\n      ✓ Successfully created {success_count}/{len(users)} users")

    # ==================== TEMPLATES MIGRATION ====================

    def get_templates_from_portal1(self) -> List[Dict]:
        """Fetch PROJECT-type templates from Portal 1"""
        print("\n   [1/3] Fetching templates from Portal 1...")

        url = f"{self.portal1_config['v1_api_base']}{self.portal1_config['endpoints']['templates']}"
        headers = {"api-key": self.portal1_config['api_key']}

        response = self._make_request("GET", url, headers)
        self.log_operation("GET_TEMPLATES", "Portal 1", url, response)

        if response["success"]:
            all_templates = response["data"] if isinstance(response["data"], list) else response["data"].get("data", [])
            # Filter by configured template object type (default: PROJECT)
            # API returns all types (TASK, FORM, DOCUMENT, MILESTONE, STATUS_UPDATE, PROJECT)
            target_type = self.migration_config.get("template_object_type", "PROJECT")
            templates = [t for t in all_templates if t.get("objectType") == target_type]
            print(f"      ✓ Fetched {len(all_templates)} total templates, filtered to {len(templates)} {target_type} templates")
            return templates
        else:
            print(f"      ✗ Error fetching templates: {response.get('error')}")
            return []

    def get_templates_from_portal2(self) -> List[Dict]:
        """Fetch templates from Portal 2 for deduplication (filtered by configured objectType)"""
        url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['templates']}"
        headers = {"api-key": self.portal2_config['api_key']}

        response = self._make_request("GET", url, headers)
        self.log_operation("GET_TEMPLATES", "Portal 2", url, response)

        if response["success"]:
            all_templates = response["data"] if isinstance(response["data"], list) else response["data"].get("data", [])
            # Same filter as Portal 1 to avoid false name collisions with other template types
            target_type = self.migration_config.get("template_object_type", "PROJECT")
            templates = [t for t in all_templates if t.get("objectType") == target_type]
            return templates
        else:
            return []

    def get_template_details_from_portal1(self, template_id: int) -> Optional[Dict]:
        """Fetch detailed template data from Portal 1"""
        endpoint = self.portal1_config['endpoints']['template_detail'].replace("{templateId}", str(template_id))
        url = f"{self.portal1_config['v1_api_base']}{endpoint}"
        headers = {"api-key": self.portal1_config['api_key']}

        response = self._make_request("GET", url, headers)

        if response["success"]:
            return response["data"]
        else:
            return None

    def remap_field_ids_in_template(self, template_data: Dict) -> Dict:
        """Remap Portal 1 field IDs and user IDs to Portal 2 IDs in template"""
        if not template_data:
            return template_data

        # Detect and log form tasks
        form_count = 0
        if "phases" in template_data:
            for phase in template_data.get("phases", []):
                for task in phase.get("tasks", []):
                    if task.get("taskType") == "FORM" or "formId" in task:
                        form_count += 1

        if form_count > 0:
            self._current_template_has_forms = form_count

        # Create mapping lookups
        field_map = {}
        if self.field_mapping:
            field_map = {
                str(v["portal1_id"]): v["portal2_id"]
                for v in self.field_mapping.values()
                if v.get("portal1_id") and v.get("portal2_id")
            }

        user_map = {}
        if self.user_mapping:
            user_map = {
                str(v["portal1_id"]): v["portal2_id"]
                for v in self.user_mapping.values()
                if v.get("portal1_id") and v.get("portal2_id")
            }

        role_map = {}
        if self.role_mapping:
            role_map = {
                str(v["portal1_id"]): v["portal2_id"]
                for v in self.role_mapping.values()
                if v.get("portal1_id") and v.get("portal2_id")
            }

        def remap_value(value, mapping):
            """Recursively remap IDs in values"""
            if isinstance(value, dict):
                return {k: remap_value(v, mapping) for k, v in value.items()}
            elif isinstance(value, list):
                return [remap_value(item, mapping) for item in value]
            elif isinstance(value, (int, str)):
                str_val = str(value)
                if str_val in mapping:
                    return mapping[str_val]
            return value

        def remap_in_dict(data):
            """Recursively remap field IDs, user IDs, and role IDs"""
            if not isinstance(data, dict):
                return data

            remapped = {}
            for key, value in data.items():
                # Remap field IDs
                if key in ["fieldId", "customFieldId", "field", "fieldID"] and value:
                    str_val = str(value)
                    remapped[key] = field_map.get(str_val, value)

                # Remap user IDs (assignees)
                # assignee can be a scalar user ID or a dict {users:[], teams:[{teamId, roleId}]}
                elif key in ["assignee", "assigneeId", "userId", "user", "createdBy", "updatedBy"] and value:
                    if isinstance(value, dict):
                        remapped[key] = remap_in_dict(value)
                    elif isinstance(value, list):
                        remapped[key] = [remap_in_dict(item) if isinstance(item, dict)
                                         else user_map.get(str(item), item) for item in value]
                    else:
                        str_val = str(value)
                        remapped[key] = user_map.get(str_val, value)

                # Remap role IDs
                # teamId in assignee.teams[] is the role's team reference — remap via role_map
                # role can be either scalar (role ID) or dict ({roleId, roleName}) — recurse if dict
                elif key in ["roleId", "role", "teamId"] and value:
                    if isinstance(value, dict):
                        remapped[key] = remap_in_dict(value)
                    elif isinstance(value, list):
                        remapped[key] = [remap_in_dict(item) if isinstance(item, dict)
                                         else role_map.get(str(item), item) for item in value]
                    else:
                        str_val = str(value)
                        remapped[key] = role_map.get(str_val, value)

                # Remap lists of IDs
                elif key in ["assignees", "userIds", "fieldIds"] and isinstance(value, list):
                    if key in ["assignees", "userIds"]:
                        remapped[key] = [user_map.get(str(uid), uid) for uid in value]
                    elif key == "fieldIds":
                        remapped[key] = [field_map.get(str(fid), fid) for fid in value]

                # Recursively process nested structures
                elif isinstance(value, dict):
                    remapped[key] = remap_in_dict(value)
                elif isinstance(value, list):
                    remapped[key] = [remap_in_dict(item) if isinstance(item, dict) else item for item in value]
                else:
                    remapped[key] = value

            return remapped

        # Remap the template data
        remapped_template = remap_in_dict(template_data)

        # Remap field IDs embedded in dynamic condition strings and rich-text content
        # e.g. "project.conditionalCustomField.460443" or data-conditionalvariables="460443"
        import re as _re
        def remap_string_field_refs(obj):
            """Recursively walk all string values and replace Portal 1 field IDs with Portal 2 IDs"""
            if isinstance(obj, dict):
                return {k: remap_string_field_refs(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [remap_string_field_refs(item) for item in obj]
            elif isinstance(obj, str) and field_map:
                result = obj
                # Replace .conditionalCustomField.<id> references
                def replace_cf(m):
                    fid = m.group(1)
                    return f".conditionalCustomField.{field_map.get(fid, fid)}"
                result = _re.sub(r'\.conditionalCustomField\.(\d+)', replace_cf, result)
                # Replace data-conditionalvariables="<id>" references
                def replace_cv(m):
                    fid = m.group(1)
                    return f'data-conditionalvariables="{field_map.get(fid, fid)}"'
                result = _re.sub(r'data-conditionalvariables="(\d+)"', replace_cv, result)
                # Replace customField.<id> references
                def replace_custom(m):
                    fid = m.group(1)
                    return f'customField.{field_map.get(fid, fid)}'
                result = _re.sub(r'customField\.(\d+)', replace_custom, result)
                return result
            return obj
        remapped_template = remap_string_field_refs(remapped_template)

        # Special handling for forms if they exist
        if "forms" in remapped_template and isinstance(remapped_template["forms"], list):
            for form in remapped_template["forms"]:
                if isinstance(form, dict):
                    # Remap form fields
                    if "fields" in form and isinstance(form["fields"], list):
                        for form_field in form["fields"]:
                            if isinstance(form_field, dict) and "fieldId" in form_field:
                                str_fid = str(form_field["fieldId"])
                                if str_fid in field_map:
                                    form_field["fieldId"] = field_map[str_fid]

        # Special handling for phases and tasks
        # Templates use templateContent.projectPhases (not top-level "phases")
        template_content = remapped_template.get("templateContent", {})
        phases_list = template_content.get("projectPhases", [])
        if phases_list and isinstance(phases_list, list):
            for phase in phases_list:
                if isinstance(phase, dict):
                    # Remap phase assignees (scalar user ID or dict)
                    if "assignee" in phase and phase["assignee"]:
                        if isinstance(phase["assignee"], dict):
                            phase["assignee"] = remap_in_dict(phase["assignee"])
                        else:
                            str_uid = str(phase["assignee"])
                            if str_uid in user_map:
                                phase["assignee"] = user_map[str_uid]

                    # Remap tasks within phases
                    if "tasks" in phase and isinstance(phase["tasks"], list):
                        for task in phase["tasks"]:
                            if isinstance(task, dict):
                                # Preserve form tasks - ensure taskType is maintained
                                if task.get("taskType") == "FORM":
                                    # Form tasks need special handling
                                    # Remap formId if it exists and references a field
                                    if "formId" in task and task["formId"]:
                                        str_fid = str(task["formId"])
                                        if str_fid in field_map:
                                            task["formId"] = field_map[str_fid]

                                    # Remap fields within the form task configuration
                                    if "formConfig" in task and isinstance(task["formConfig"], dict):
                                        form_config = task["formConfig"]
                                        if "fields" in form_config and isinstance(form_config["fields"], list):
                                            for form_field in form_config["fields"]:
                                                if isinstance(form_field, dict) and "fieldId" in form_field:
                                                    str_fid = str(form_field["fieldId"])
                                                    if str_fid in field_map:
                                                        form_field["fieldId"] = field_map[str_fid]

                                # Remap task assignee (scalar user ID or dict)
                                if "assignee" in task and task["assignee"]:
                                    if isinstance(task["assignee"], dict):
                                        task["assignee"] = remap_in_dict(task["assignee"])
                                    else:
                                        str_uid = str(task["assignee"])
                                        if str_uid in user_map:
                                            task["assignee"] = user_map[str_uid]

                                # Remap custom fields in task
                                if "customFields" in task and isinstance(task["customFields"], list):
                                    for cf in task["customFields"]:
                                        if isinstance(cf, dict) and "fieldId" in cf:
                                            str_fid = str(cf["fieldId"])
                                            if str_fid in field_map:
                                                cf["fieldId"] = field_map[str_fid]

        return remapped_template

    def create_template_in_portal2(self, template: Dict) -> Optional[Dict]:
        """Create a template in Portal 2"""
        url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['templates']}"
        headers = {"api-key": self.portal2_config['api_key']}

        # Get detailed template data
        template_details = self.get_template_details_from_portal1(template.get("templateId"))
        if not template_details:
            print(f"      ✗ Could not fetch details: {template.get('templateName')}")
            return None

        # Remap field IDs
        self._current_template_has_forms = 0
        remapped_template = self.remap_field_ids_in_template(template_details)
        has_forms = self._current_template_has_forms > 0

        # Prepare request data (remove Portal 1 specific fields)
        excluded_fields = ["templateId", "accountId", "createdAt", "updatedAt", "createdBy", "updatedBy"]
        request_data = {k: v for k, v in remapped_template.items() if k not in excluded_fields}

        # Additional cleanup for known problematic fields
        request_data = {k: v for k, v in request_data.items() if v is not None}

        # Recursively filter out invalid field names throughout the data structure
        def clean_invalid_fields(data):
            """Recursively remove fields with invalid names (starting with < or other special chars)"""
            if isinstance(data, dict):
                cleaned = {}
                for k, v in data.items():
                    # Skip fields with invalid names
                    if k and (k.startswith('<') or k.startswith('>')):
                        continue
                    cleaned[k] = clean_invalid_fields(v)
                return cleaned
            elif isinstance(data, list):
                return [clean_invalid_fields(item) for item in data]
            else:
                return data

        request_data = clean_invalid_fields(request_data)

        response = self._make_request("POST", url, headers, request_data)
        self.log_operation("CREATE_TEMPLATE", "Portal 2", url, response,
                           template_id=template.get("templateId"),
                           resource_id=template.get("templateId"),
                           resource_name=template.get("templateName"),
                           request_data={"templateName": template.get("templateName")})

        if response["success"]:
            created_template = response["data"]

            # Store mapping
            self.template_mapping[str(template["templateId"])] = {
                "portal1_id": template["templateId"],
                "portal2_id": created_template.get("templateId"),
                "templateName": template.get("templateName")
            }

            form_indicator = " +forms" if has_forms else ""
            print(f"      ✓ {template.get('templateName')}{form_indicator}")
            return created_template
        else:
            status_code = response.get('status_code', 'N/A')
            print(f"      ✗ {template.get('templateName')} ({status_code})")
            return None

    def migrate_templates(self, dry_run: bool = False):
        """Migrate all templates with deduplication"""
        print("\n" + "=" * 80)
        print("STEP 5: TEMPLATES MIGRATION")
        print("=" * 80)

        # Fetch templates from Portal 1
        templates_p1 = self.get_templates_from_portal1()
        if not templates_p1:
            print("   ⚠ No templates to migrate")
            return

        # Fetch existing templates from Portal 2 for deduplication
        print("\n   [2/3] Checking existing templates in Portal 2...")
        templates_p2 = self.get_templates_from_portal2()

        # Create lookup by name for Portal 2 templates
        p2_template_names = {t.get('templateName'): t for t in templates_p2}
        print(f"      ✓ Found {len(p2_template_names)} existing templates in Portal 2")

        # Load previous migration mapping if exists
        previous_mapping = {}
        if os.path.exists(self.logging_config.get('template_mapping', 'template_mapping.json')):
            try:
                with open(self.logging_config['template_mapping'], 'r') as f:
                    previous_mapping = json.load(f)
                print(f"      ✓ Loaded previous migration mapping ({len(previous_mapping)} records)")
            except:
                pass

        # Categorize templates
        to_create = []
        to_skip = []
        already_migrated = []

        for template in templates_p1:
            name = template.get('templateName')
            template_id = template.get('templateId')
            mapping_key = f"template_{template_id}"

            # Check if template exists in Portal 2
            exists_in_p2 = name in p2_template_names

            # Check if previously migrated
            was_migrated = mapping_key in previous_mapping

            if exists_in_p2 and was_migrated:
                # Already migrated in previous run - skip
                already_migrated.append(name)
            elif exists_in_p2 and not was_migrated:
                # Exists in Portal 2 but not in our mapping - user created, skip
                to_skip.append(name)
            else:
                # Doesn't exist in Portal 2 - create it
                to_create.append(template)

        print(f"\n   Migration plan:")
        print(f"      - To create: {len(to_create)}")
        print(f"      - Already migrated (skip): {len(already_migrated)}")
        print(f"      - User-created (skip): {len(to_skip)}")

        if dry_run:
            print(f"\n   [3/3] DRY RUN - Would create {len(to_create)} templates")
            if already_migrated:
                print(f"\n   Would skip {len(already_migrated)} already migrated templates")
            if to_skip:
                print(f"\n   Would skip {len(to_skip)} user-created templates")
            return

        # Create new templates
        if to_create:
            print(f"\n   [3/3] Creating {len(to_create)} new templates in Portal 2...")
            success_count = 0
            templates_with_forms = []
            for template in to_create:
                result = self.create_template_in_portal2(template)
                if result:
                    success_count += 1
                    if self._current_template_has_forms > 0:
                        templates_with_forms.append(template.get('templateName'))
                time.sleep(self.rate_limits.get('template_creation', 0.2))

            print(f"\n      ✓ Successfully created {success_count}/{len(to_create)} templates")
            if templates_with_forms:
                print(f"      ✓ {len(templates_with_forms)} template(s) with forms migrated successfully")
                for tname in templates_with_forms[:5]:
                    print(f"         - {tname}")
                if len(templates_with_forms) > 5:
                    print(f"         ... and {len(templates_with_forms) - 5} more")
        else:
            print(f"\n   ✓ No new templates to create")

        if already_migrated:
            print(f"\n      ℹ Skipped {len(already_migrated)} already migrated templates")
        if to_skip:
            print(f"      ℹ Skipped {len(to_skip)} user-created templates")

    # ==================== DEPENDENCIES MIGRATION ====================

    def get_dependency_map_from_portal1(self, template_ids: List[int]) -> Dict:
        """Fetch dependency map for templates from Portal 1"""
        print("\n   [1/2] Fetching dependency map from Portal 1...")

        url = f"{self.portal1_config['v1_api_base']}{self.portal1_config['endpoints']['template_dependencies']}"
        headers = {"api-key": self.portal1_config['api_key']}
        request_data = {"templateIds": template_ids}

        response = self._make_request("POST", url, headers, request_data)
        self.log_operation("GET_DEPENDENCY_MAP", "Portal 1", url, response, request_data=request_data)

        if response["success"]:
            print(f"      ✓ Fetched dependency map from Portal 1")
            return response["data"]
        else:
            print(f"      ✗ Error fetching dependency map: {response.get('error')}")
            return {}

    def remap_dependencies(self, dependency_map: Dict) -> Dict:
        """Remap task and phase IDs in dependency map"""
        if not dependency_map:
            return {}

        # TODO: Implement ID remapping for dependencies
        # This would need to use template_mapping to remap task and phase IDs

        return dependency_map

    def create_dependency_map_in_portal2(self, dependency_map: Dict) -> bool:
        """Create dependency map in Portal 2"""
        url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['template_dependencies']}"
        headers = {"api-key": self.portal2_config['api_key']}

        response = self._make_request("POST", url, headers, dependency_map)
        self.log_operation("CREATE_DEPENDENCY_MAP", "Portal 2", url, response, request_data=dependency_map)

        if response["success"]:
            print(f"      ✓ Created dependency map in Portal 2")
            return True
        else:
            print(f"      ✗ Failed to create dependency map: {response.get('error')}")
            return False

    def migrate_dependencies(self, dry_run: bool = False):
        """Migrate template dependencies"""
        print("\n" + "=" * 80)
        print("STEP 6: DEPENDENCIES MIGRATION")
        print("=" * 80)

        if not self.template_mapping:
            print("   ⚠ No templates migrated, skipping dependencies")
            return

        # Get Portal 1 template IDs
        portal1_template_ids = [v["portal1_id"] for v in self.template_mapping.values()]

        dependency_map = self.get_dependency_map_from_portal1(portal1_template_ids)
        if not dependency_map:
            print("   ⚠ No dependencies to migrate")
            return

        if dry_run:
            print(f"\n   [2/2] DRY RUN - Would create dependency map")
            return

        print(f"\n   [2/2] Creating dependency map in Portal 2...")
        remapped_dependencies = self.remap_dependencies(dependency_map)
        self.create_dependency_map_in_portal2(remapped_dependencies)

    # ==================== AUTOMATIONS MIGRATION ====================

    def get_automations_from_portal1(self) -> List[Dict]:
        """Fetch all global automations from Portal 1"""
        print("\n   [1/3] Fetching automations list from Portal 1...")

        url = f"{self.portal1_config['v1_api_base']}{self.portal1_config['endpoints']['automations_global']}"
        headers = {"api-key": self.portal1_config.get('automation_api_key', self.portal1_config['api_key'])}

        response = self._make_request("GET", url, headers)
        self.log_operation("GET_AUTOMATIONS", "Portal 1", url, response)

        if response["success"]:
            automations = response["data"] if isinstance(response["data"], list) else response["data"].get("data", [])
            print(f"      ✓ Fetched {len(automations)} automations from Portal 1")
            return automations
        else:
            print(f"      ✗ Error fetching automations: {response.get('error')}")
            return []

    def get_automations_from_portal2(self) -> List[Dict]:
        """Fetch all global automations from Portal 2 for deduplication"""
        url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['automations_global']}"
        headers = {"api-key": self.portal2_config['api_key']}

        response = self._make_request("GET", url, headers)
        self.log_operation("GET_AUTOMATIONS", "Portal 2", url, response)

        if response["success"]:
            automations = response["data"] if isinstance(response["data"], list) else response["data"].get("data", [])
            return automations
        else:
            return []

    def get_automation_details_from_portal1(self, automation_id: int) -> Optional[Dict]:
        """Fetch detailed automation data from Portal 1 including actionBlocks"""
        # Correct endpoint: /api/v1/automations/{id} (NOT /api/v1/automations/global/{id})
        endpoint = f"/api/v1/automations/{automation_id}"
        url = f"{self.portal1_config['v1_api_base']}{endpoint}"
        headers = {"api-key": self.portal1_config.get('automation_api_key', self.portal1_config['api_key'])}

        response = self._make_request("GET", url, headers)
        self.log_operation("GET_AUTOMATION_DETAIL", "Portal 1", url, response, automation_id=automation_id)

        if response["success"]:
            return response["data"]
        return None

    def remap_ids_in_automation(self, automation: Dict) -> Dict:
        """Remap Portal 1 field IDs, user IDs, role IDs, and template IDs to Portal 2 IDs in automation"""
        if not automation:
            return automation

        # Create mapping lookups
        field_map = {}
        if self.field_mapping:
            field_map = {
                str(v["portal1_id"]): v["portal2_id"]
                for v in self.field_mapping.values()
                if v.get("portal1_id") and v.get("portal2_id")
            }

        user_map = {}
        if self.user_mapping:
            user_map = {
                str(v["portal1_id"]): v["portal2_id"]
                for v in self.user_mapping.values()
                if v.get("portal1_id") and v.get("portal2_id")
            }

        role_map = {}
        if self.role_mapping:
            role_map = {
                str(v["portal1_id"]): v["portal2_id"]
                for v in self.role_mapping.values()
                if v.get("portal1_id") and v.get("portal2_id")
            }

        template_map = {}
        if self.template_mapping:
            template_map = {
                str(v["portal1_id"]): v["portal2_id"]
                for v in self.template_mapping.values()
                if v.get("portal1_id") and v.get("portal2_id")
            }

        def remap_in_structure(data):
            """Recursively remap IDs in automation structure"""
            if isinstance(data, dict):
                remapped = {}
                for key, value in data.items():
                    # Remap field IDs
                    if key in ["fieldId", "customFieldId", "field", "fieldID"] and value:
                        str_val = str(value)
                        remapped[key] = field_map.get(str_val, value)

                    # Remap user IDs
                    elif key in ["userId", "assignee", "assigneeId", "user", "createdBy", "updatedBy"] and value:
                        str_val = str(value)
                        remapped[key] = user_map.get(str_val, value)

                    # Remap role IDs
                    elif key in ["roleId", "role"] and value:
                        str_val = str(value)
                        remapped[key] = role_map.get(str_val, value)

                    # Remap template IDs in automation actions (e.g., IMPORT_TEMPLATE action)
                    elif key == "templateId" and isinstance(value, dict) and value.get("objectType") == "PROJECT_TEMPLATE":
                        object_id = value.get("objectId")
                        if object_id:
                            str_id = str(object_id)
                            if str_id in template_map:
                                remapped[key] = {**value, "objectId": str(template_map[str_id])}
                            else:
                                remapped[key] = value
                        else:
                            remapped[key] = value

                    # Remap lists
                    elif isinstance(value, list):
                        remapped[key] = [remap_in_structure(item) for item in value]

                    # Recursively process nested dicts
                    elif isinstance(value, dict):
                        remapped[key] = remap_in_structure(value)

                    else:
                        remapped[key] = value

                return remapped

            elif isinstance(data, list):
                return [remap_in_structure(item) for item in data]

            else:
                return data

        # Remap the automation data
        remapped_automation = remap_in_structure(automation)

        return remapped_automation

    def create_automation_in_portal2(self, automation: Dict) -> Optional[Dict]:
        """Create an automation in Portal 2"""
        url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['automations_global']}"
        headers = {"api-key": self.portal2_config['api_key']}

        # Fetch full automation details including actionBlocks
        automation_id = automation.get('automationId')
        automation_details = self.get_automation_details_from_portal1(automation_id)

        if not automation_details:
            print(f"      ✗ Could not fetch details: {automation.get('automationName')}")
            return None

        # Remap field IDs, user IDs, role IDs, and template IDs in automation
        remapped_automation = self.remap_ids_in_automation(automation_details)

        # Prepare automation data (remove Portal 1 specific IDs)
        excluded_fields = ["automationId", "accountId", "createdAt", "updatedAt", "createdBy", "order",
                          "sourceId", "configMeta", "placeholders"]
        request_data = {k: v for k, v in remapped_automation.items() if k not in excluded_fields}

        # Set to disabled state for user to review
        request_data["enabled"] = False

        response = self._make_request("POST", url, headers, request_data)
        self.log_operation("CREATE_AUTOMATION", "Portal 2", url, response,
                           request_data=request_data,
                           resource_id=automation.get("automationId"),
                           resource_name=automation.get("automationName"))

        if response["success"]:
            created_automation = response["data"]

            # Store mapping
            mapping_key = f"automation_{automation_id}"
            self.automation_mapping[mapping_key] = {
                "portal1": {
                    "automationId": automation_id,
                    "automationName": automation.get("automationName"),
                    "automationType": automation.get("automationType")
                },
                "portal2": created_automation,
                "migration_timestamp": datetime.now().isoformat()
            }

            print(f"      ✓ {request_data.get('automationName')} (disabled)")
            return created_automation
        else:
            status_code = response.get('status_code', 'N/A')
            print(f"      ✗ {request_data.get('automationName')} ({status_code})")
            return None

    def migrate_automations(self, dry_run: bool = False):
        """Migrate all global automations with deduplication"""
        print("\n" + "=" * 80)
        print("STEP 7: AUTOMATIONS MIGRATION")
        print("=" * 80)
        print("   NOTE: Automations will be created in DISABLED state")
        print("   → Review and enable automations in Portal 2 after migration")

        # Fetch automations from Portal 1
        automations_p1 = self.get_automations_from_portal1()
        if not automations_p1:
            print("   ⚠ No automations to migrate")
            return

        # Fetch existing automations from Portal 2 for deduplication
        print("\n   [2/3] Checking existing automations in Portal 2...")
        automations_p2 = self.get_automations_from_portal2()

        # Create lookup by name for Portal 2 automations
        p2_automation_names = {a.get('automationName'): a for a in automations_p2}
        print(f"      ✓ Found {len(p2_automation_names)} existing automations in Portal 2")

        # Load previous migration mapping if exists
        previous_mapping = {}
        if os.path.exists(self.logging_config.get('automation_mapping', 'automation_mapping.json')):
            try:
                with open(self.logging_config['automation_mapping'], 'r') as f:
                    previous_mapping = json.load(f)
                print(f"      ✓ Loaded previous migration mapping ({len(previous_mapping)} records)")
            except:
                pass

        # Categorize automations
        to_create = []
        to_skip = []
        already_migrated = []

        for automation in automations_p1:
            name = automation.get('automationName')
            automation_id = automation.get('automationId')
            mapping_key = f"automation_{automation_id}"

            # Check if automation exists in Portal 2
            exists_in_p2 = name in p2_automation_names

            # Check if previously migrated
            was_migrated = mapping_key in previous_mapping

            if exists_in_p2 and was_migrated:
                # Already migrated in previous run - skip
                already_migrated.append(name)
            elif exists_in_p2 and not was_migrated:
                # Exists in Portal 2 but not in our mapping - user created, skip
                to_skip.append(name)
            else:
                # Doesn't exist in Portal 2 - create it
                to_create.append(automation)

        print(f"\n   Migration plan:")
        print(f"      - To create: {len(to_create)}")
        print(f"      - Already migrated (skip): {len(already_migrated)}")
        print(f"      - User-created (skip): {len(to_skip)}")

        if dry_run:
            print(f"\n   [3/3] DRY RUN - Would create {len(to_create)} automations:")
            for automation in to_create[:10]:
                print(f"         - {automation.get('automationName')} ({automation.get('automationType')})")
            if len(to_create) > 10:
                print(f"         ... and {len(to_create) - 10} more automations")

            if already_migrated:
                print(f"\n   Would skip {len(already_migrated)} already migrated automations")
            if to_skip:
                print(f"\n   Would skip {len(to_skip)} user-created automations")
            return

        # Create new automations
        if to_create:
            print(f"\n   [3/3] Creating {len(to_create)} new automations in Portal 2...")
            success_count = 0
            for automation in to_create:
                if self.create_automation_in_portal2(automation):
                    success_count += 1
                time.sleep(self.rate_limits.get('automation_creation', 0.2))

            print(f"\n      ✓ Successfully created {success_count}/{len(to_create)} automations")
        else:
            print(f"\n   ✓ No new automations to create")

        if already_migrated:
            print(f"\n      ℹ Skipped {len(already_migrated)} already migrated automations")
        if to_skip:
            print(f"      ℹ Skipped {len(to_skip)} user-created automations")

        print(f"\n      ⚠ All migrated automations are in DISABLED state - review and enable in Portal 2")

    # ==================== TIMESHEETS MIGRATION ====================

    def get_timesheet_configuration_from_portal1(self) -> Optional[Dict]:
        """Fetch timesheet configuration from Portal 1"""
        print("\n   [1/7] Fetching timesheet configuration from Portal 1...")

        url = f"{self.portal1_config['v1_api_base']}{self.portal1_config['endpoints']['timesheets_configuration']}"
        headers = {"api-key": self.portal1_config['api_key']}

        response = self._make_request("GET", url, headers)
        self.log_operation("GET_TIMESHEET_CONFIG", "Portal 1", url, response)

        if response["success"]:
            config = response["data"]
            print(f"      ✓ Fetched timesheet configuration from Portal 1")
            return config
        else:
            print(f"      ✗ Error fetching timesheet configuration: {response.get('error')}")
            return None

    def update_timesheet_configuration_in_portal2(self, config: Dict, dry_run: bool = False) -> bool:
        """Update timesheet configuration in Portal 2"""
        if dry_run:
            print("      DRY RUN - Would update timesheet configuration")
            return True

        print("\n   [2/7] Updating timesheet configuration in Portal 2...")

        url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['timesheets_configuration']}"
        headers = {"api-key": self.portal2_config['api_key']}

        # Remove portal-specific fields
        clean_config = {k: v for k, v in config.items() if k != 'timeSheetConfigId'}

        response = self._make_request("PUT", url, headers, clean_config)
        self.log_operation("UPDATE_TIMESHEET_CONFIG", "Portal 2", url, response, request_data=clean_config)

        if response["success"]:
            self.timesheet_mapping["configuration"] = {
                "portal1": config,
                "portal2": response["data"],
                "migration_timestamp": datetime.now().isoformat()
            }
            print(f"      ✓ Updated timesheet configuration in Portal 2")
            return True
        else:
            print(f"      ✗ Failed to update timesheet configuration: {response.get('error')}")
            return False

    def get_timesheet_categories_from_portal1(self) -> List[Dict]:
        """Fetch timesheet categories from Portal 1"""
        print("\n   [3/7] Fetching timesheet categories from Portal 1...")

        url = f"{self.portal1_config['v1_api_base']}{self.portal1_config['endpoints']['timesheets_categories']}"
        headers = {"api-key": self.portal1_config['api_key']}

        response = self._make_request("GET", url, headers)
        self.log_operation("GET_TIMESHEET_CATEGORIES", "Portal 1", url, response)

        if response["success"]:
            categories = response["data"] if isinstance(response["data"], list) else response["data"].get("data", [])
            print(f"      ✓ Fetched {len(categories)} timesheet categories from Portal 1")
            return categories
        else:
            print(f"      ✗ Error fetching timesheet categories: {response.get('error')}")
            return []

    def create_timesheet_category_in_portal2(self, category: Dict) -> Optional[Dict]:
        """Create a timesheet category in Portal 2"""
        url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['timesheets_categories']}"
        headers = {"api-key": self.portal2_config['api_key']}

        request_data = {
            "categoryName": category.get("categoryName")
        }

        response = self._make_request("POST", url, headers, request_data)
        self.log_operation("CREATE_TIMESHEET_CATEGORY", "Portal 2", url, response, request_data=request_data)

        if response["success"]:
            created_category = response["data"]

            # Store mapping
            mapping_key = f"category_{category.get('categoryId', category.get('categoryName'))}"
            self.timesheet_mapping["categories"][mapping_key] = {
                "portal1": category,
                "portal2": created_category,
                "migration_timestamp": datetime.now().isoformat()
            }

            print(f"      ✓ {request_data.get('categoryName')}")
            return created_category
        else:
            status_code = response.get('status_code', 'N/A')
            print(f"      ✗ {request_data.get('categoryName')} ({status_code})")
            return None

    def get_timesheet_activities_from_portal1(self, activity_type: str) -> List[Dict]:
        """Fetch timesheet activities from Portal 1"""
        print(f"\n   [{5 if activity_type == 'NON_PROJECT' else 6}/7] Fetching {activity_type} activities from Portal 1...")

        url = f"{self.portal1_config['v1_api_base']}{self.portal1_config['endpoints']['timesheets_activity']}?type={activity_type}"
        headers = {"api-key": self.portal1_config['api_key']}

        response = self._make_request("GET", url, headers)
        self.log_operation(f"GET_TIMESHEET_ACTIVITIES_{activity_type}", "Portal 1", url, response)

        if response["success"]:
            activities = response["data"] if isinstance(response["data"], list) else response["data"].get("data", [])
            print(f"      ✓ Fetched {len(activities)} {activity_type} activities from Portal 1")
            return activities
        else:
            print(f"      ✗ Error fetching {activity_type} activities: {response.get('error')}")
            return []

    def create_timesheet_activity_in_portal2(self, activity: Dict) -> Optional[Dict]:
        """Create a timesheet activity in Portal 2"""
        url = f"{self.portal2_config['api_base']}{self.portal2_config['endpoints']['timesheets_activity']}"
        headers = {"api-key": self.portal2_config['api_key']}

        request_data = {
            "activityName": activity.get("activityName"),
            "type": activity.get("type")
        }

        response = self._make_request("POST", url, headers, request_data)
        self.log_operation("CREATE_TIMESHEET_ACTIVITY", "Portal 2", url, response, request_data=request_data)

        if response["success"]:
            created_activity = response["data"]

            # Store mapping
            mapping_key = f"activity_{activity.get('activityId', activity.get('activityName'))}_{activity.get('type')}"
            self.timesheet_mapping["activities"][mapping_key] = {
                "portal1": activity,
                "portal2": created_activity,
                "migration_timestamp": datetime.now().isoformat()
            }

            print(f"      ✓ {request_data.get('activityName')} ({request_data.get('type')})")
            return created_activity
        else:
            status_code = response.get('status_code', 'N/A')
            print(f"      ✗ {request_data.get('activityName')} ({status_code})")
            return None

    def migrate_timesheets(self, dry_run: bool = False):
        """Migrate timesheet configuration, categories, and activities"""
        print("\n" + "=" * 80)
        print("STEP 8: TIMESHEETS MIGRATION")
        print("=" * 80)

        # Part 1: Configuration
        config = self.get_timesheet_configuration_from_portal1()
        if config:
            self.update_timesheet_configuration_in_portal2(config, dry_run)

        # Part 2: Categories
        categories = self.get_timesheet_categories_from_portal1()
        if dry_run:
            print(f"\n   [4/7] DRY RUN - Would create {len(categories)} timesheet categories")
        elif categories:
            print(f"\n   [4/7] Creating {len(categories)} timesheet categories in Portal 2...")
            success_count = 0
            for category in categories:
                if self.create_timesheet_category_in_portal2(category):
                    success_count += 1
                time.sleep(self.rate_limits.get('timesheet_creation', 0.2))
            print(f"\n      ✓ Successfully created {success_count}/{len(categories)} categories")

        # Part 3: Non-Project Activities
        non_project_activities = self.get_timesheet_activities_from_portal1("NON_PROJECT")
        if dry_run:
            print(f"      DRY RUN - Would create {len(non_project_activities)} NON_PROJECT activities")
        elif non_project_activities:
            success_count = 0
            for activity in non_project_activities:
                if self.create_timesheet_activity_in_portal2(activity):
                    success_count += 1
                time.sleep(self.rate_limits.get('timesheet_creation', 0.2))
            print(f"      ✓ Successfully created {success_count}/{len(non_project_activities)} NON_PROJECT activities")

        # Part 4: Project Activities
        project_activities = self.get_timesheet_activities_from_portal1("PROJECT")
        if dry_run:
            print(f"\n   [7/7] DRY RUN - Would create {len(project_activities)} PROJECT activities")
        elif project_activities:
            print(f"\n   [7/7] Creating {len(project_activities)} PROJECT activities in Portal 2...")
            success_count = 0
            for activity in project_activities:
                if self.create_timesheet_activity_in_portal2(activity):
                    success_count += 1
                time.sleep(self.rate_limits.get('timesheet_creation', 0.2))
            print(f"\n      ✓ Successfully created {success_count}/{len(project_activities)} PROJECT activities")

    # ==================== MAIN MIGRATION ====================

    def create_migration_report(self, dry_run: bool = False):
        """Create detailed migration report in a named folder under the customer directory"""
        # Save reports inside the customer directory
        customer_dir = self.logging_config.get("customer_directory", "customers/default")
        base_dir = os.path.join(customer_dir, "migrations")
        os.makedirs(base_dir, exist_ok=True)

        # Create folder with timestamp and mode
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode = "dry_run" if dry_run else "live"

        # Clean portal names for folder name (remove spaces and special chars)
        source_name = self.portal1_config['name'].replace(' ', '_').replace('/', '_')
        dest_name = self.portal2_config['name'].replace(' ', '_').replace('/', '_')

        migration_dir = os.path.join(base_dir, f"{source_name}_to_{dest_name}_{mode}_{timestamp}")
        os.makedirs(migration_dir, exist_ok=True)

        print(f"\n📁 Creating migration report in: {migration_dir}/")

        # Generate CSV files for each entity type
        self._save_fields_report(migration_dir)
        self._save_roles_report(migration_dir)
        self._save_skills_report(migration_dir)
        self._save_templates_report(migration_dir)
        self._save_automations_report(migration_dir)
        self._save_timesheets_report(migration_dir)
        self._save_summary_report(migration_dir, dry_run)
        self._save_cloned_report(migration_dir, dry_run)
        self._save_not_cloned_report(migration_dir, dry_run)

        print(f"✅ Migration report saved to: {migration_dir}/")
        return migration_dir

    def _save_fields_report(self, migration_dir: str):
        """Save fields migration report as readable text"""
        if not self.field_mapping:
            return

        txt_file = os.path.join(migration_dir, "fields.txt")
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("FIELDS MIGRATED\n")
            f.write("=" * 80 + "\n\n")

            # Group by object type
            by_type = {}
            for mapping in self.field_mapping.values():
                obj_type = mapping.get('objectType', 'Unknown')
                if obj_type not in by_type:
                    by_type[obj_type] = []
                by_type[obj_type].append(mapping)

            for obj_type, fields in sorted(by_type.items()):
                f.write(f"\n{obj_type} Fields:\n")
                f.write("-" * 40 + "\n")
                for mapping in sorted(fields, key=lambda x: x.get('fieldLabel', '')):
                    status = "✓ Mapped" if mapping.get('matched') else "✓ Created"
                    f.write(f"  {status} {mapping.get('fieldLabel', 'Unknown')} ({mapping.get('fieldType', 'Unknown')})\n")

            f.write(f"\n\nTotal: {len(self.field_mapping)} fields\n")

        print(f"   ✓ Fields report: fields.txt ({len(self.field_mapping)} fields)")

    def _save_roles_report(self, migration_dir: str):
        """Save roles migration report as readable text"""
        if not self.role_mapping:
            return

        txt_file = os.path.join(migration_dir, "roles.txt")
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("ROLES MIGRATED\n")
            f.write("=" * 80 + "\n\n")

            for mapping in sorted(self.role_mapping.values(), key=lambda x: x.get('roleName', '')):
                status = "✓ Mapped" if mapping.get('matched') else "✓ Created"
                f.write(f"  {status} {mapping.get('roleName', 'Unknown')}\n")

            f.write(f"\n\nTotal: {len(self.role_mapping)} roles\n")

        print(f"   ✓ Roles report: roles.txt ({len(self.role_mapping)} roles)")

    def _save_skills_report(self, migration_dir: str):
        """Save skills migration report as readable text"""
        if not self.skill_mapping:
            return

        txt_file = os.path.join(migration_dir, "skills.txt")
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("SKILLS MIGRATED\n")
            f.write("=" * 80 + "\n\n")

            for mapping in sorted(self.skill_mapping.values(), key=lambda x: x.get('skillName', '')):
                status = "✓ Mapped" if mapping.get('matched') else "✓ Created"
                f.write(f"  {status} {mapping.get('skillName', 'Unknown')}\n")

            f.write(f"\n\nTotal: {len(self.skill_mapping)} skills\n")

        print(f"   ✓ Skills report: skills.txt ({len(self.skill_mapping)} skills)")

    def _save_templates_report(self, migration_dir: str):
        """Save templates migration report as readable text"""
        if not self.template_mapping:
            return

        txt_file = os.path.join(migration_dir, "templates.txt")
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("TEMPLATES MIGRATED\n")
            f.write("=" * 80 + "\n\n")

            for mapping in sorted(self.template_mapping.values(), key=lambda x: x.get('templateName', '')):
                has_forms = " (with forms)" if mapping.get('has_forms') else ""
                template_type = mapping.get('templateType', 'Unknown')
                f.write(f"  ✓ {mapping.get('templateName', 'Unknown')} [{template_type}]{has_forms}\n")

            f.write(f"\n\nTotal: {len(self.template_mapping)} templates\n")

        print(f"   ✓ Templates report: templates.txt ({len(self.template_mapping)} templates)")

    def _save_automations_report(self, migration_dir: str):
        """Save automations migration report as readable text"""
        if not self.automation_mapping:
            return

        txt_file = os.path.join(migration_dir, "automations.txt")
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("AUTOMATIONS MIGRATED\n")
            f.write("=" * 80 + "\n\n")
            f.write("Note: All automations are created in DISABLED state for review\n\n")

            for mapping in sorted(self.automation_mapping.values(), key=lambda x: x.get('automationName', '')):
                f.write(f"  ✓ {mapping.get('automationName', 'Unknown')} (disabled)\n")

            f.write(f"\n\nTotal: {len(self.automation_mapping)} automations\n")

        print(f"   ✓ Automations report: automations.txt ({len(self.automation_mapping)} automations)")

    def _save_timesheets_report(self, migration_dir: str):
        """Save timesheets migration report as readable text"""
        config = self.timesheet_mapping.get("configuration") or {}
        categories = self.timesheet_mapping.get("categories") or {}
        activities = self.timesheet_mapping.get("activities") or {}

        if not config and not categories and not activities:
            return

        txt_file = os.path.join(migration_dir, "timesheets.txt")
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("TIMESHEETS MIGRATED\n")
            f.write("=" * 80 + "\n\n")

            f.write("Configuration:\n")
            f.write("-" * 40 + "\n")
            f.write("  ✓ Updated\n\n" if config else "  (not migrated)\n\n")

            f.write(f"Categories ({len(categories)}):\n")
            f.write("-" * 40 + "\n")
            for entry in categories.values():
                name = (entry.get("portal1") or {}).get("categoryName", "Unknown")
                f.write(f"  ✓ {name}\n")

            f.write(f"\nActivities ({len(activities)}):\n")
            f.write("-" * 40 + "\n")
            for entry in activities.values():
                p1 = entry.get("portal1") or {}
                f.write(f"  ✓ {p1.get('activityName', 'Unknown')} ({p1.get('type', 'Unknown')})\n")

            total = len(categories) + len(activities) + (1 if config else 0)
            f.write(f"\n\nTotal: {total} timesheet items\n")

        print(f"   ✓ Timesheets report: timesheets.txt "
              f"({len(categories)} categories, {len(activities)} activities)")

    def _save_cloned_report(self, migration_dir: str, dry_run: bool):
        """Consolidated report of everything actually created in Portal 2 this run"""
        # Created == present in the mapping without the "matched" flag, which is
        # only set for items that already existed in Portal 2 and were mapped.
        # Entries loaded from a previous run's JSON were created then, not now
        prior_fields = self.loaded_mapping_keys.get('field_mapping', set())
        prior_roles = self.loaded_mapping_keys.get('role_mapping', set())

        fields_created = [m for k, m in self.field_mapping.items()
                          if not m.get('matched') and k not in prior_fields]
        fields_mapped = [m for m in self.field_mapping.values() if m.get('matched')]
        roles_created = [m for k, m in self.role_mapping.items()
                         if not m.get('matched') and k not in prior_roles]
        roles_mapped = [m for m in self.role_mapping.values() if m.get('matched')]
        # Templates/automations only enter their mapping on successful creation
        templates_created = list(self.template_mapping.values())
        automations_created = list(self.automation_mapping.values())
        categories = self.timesheet_mapping.get("categories") or {}
        activities = self.timesheet_mapping.get("activities") or {}
        ts_config = self.timesheet_mapping.get("configuration") or {}

        total_created = (len(fields_created) + len(self.created_sections) + len(roles_created)
                         + len(templates_created) + len(automations_created)
                         + len(categories) + len(activities) + (1 if ts_config else 0))

        txt_file = os.path.join(migration_dir, "CLONED.txt")
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("CONFIGURATIONS CLONED\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Date & Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Mode: {'DRY RUN' if dry_run else 'LIVE MIGRATION'}\n")
            f.write(f"Source Portal: {self.portal1_config['name']}\n")
            f.write(f"Destination Portal: {self.portal2_config['name']}\n")
            if dry_run:
                f.write("\nNOTE: DRY RUN — nothing was actually created.\n")
            f.write("\n" + "=" * 80 + "\n")
            f.write("SUMMARY\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Total items created in destination: {total_created}\n")
            f.write(f"  - Fields: {len(fields_created)}\n")
            f.write(f"  - Field sections: {len(self.created_sections)}\n")
            f.write(f"  - Roles: {len(roles_created)}\n")
            f.write(f"  - Templates: {len(templates_created)}\n")
            f.write(f"  - Automations: {len(automations_created)}\n")
            f.write(f"  - Timesheet configuration: {1 if ts_config else 0}\n")
            f.write(f"  - Timesheet categories: {len(categories)}\n")
            f.write(f"  - Timesheet activities: {len(activities)}\n")
            f.write(f"\nAlready existed in destination and mapped (not re-created):\n")
            f.write(f"  - Fields: {len(fields_mapped)}\n")
            f.write(f"  - Roles: {len(roles_mapped)}\n")

            if fields_created:
                f.write("\n" + "=" * 80 + "\n")
                f.write("CREATED: FIELDS\n")
                f.write("=" * 80 + "\n")
                by_type = {}
                for m in fields_created:
                    by_type.setdefault(m.get('objectType', 'Unknown'), []).append(m)
                for obj_type, items in sorted(by_type.items()):
                    f.write(f"\n{obj_type} ({len(items)}):\n")
                    f.write("-" * 40 + "\n")
                    for m in sorted(items, key=lambda x: x.get('fieldLabel') or ''):
                        f.write(f"  ✓ {m.get('fieldLabel')}  "
                                f"[P1:{m.get('portal1_id')} → P2:{m.get('portal2_id')}]\n")

            if self.created_sections:
                f.write("\n" + "=" * 80 + "\n")
                f.write("CREATED: FIELD SECTIONS\n")
                f.write("=" * 80 + "\n\n")
                for s in self.created_sections:
                    f.write(f"  ✓ {s['fieldSectionName']} ({s['fieldSectionType']})  "
                            f"[P1:{s['portal1_id']} → P2:{s['portal2_id']}]\n")

            if roles_created:
                f.write("\n" + "=" * 80 + "\n")
                f.write("CREATED: ROLES\n")
                f.write("=" * 80 + "\n\n")
                for m in sorted(roles_created, key=lambda x: x.get('roleName') or ''):
                    f.write(f"  ✓ {m.get('roleName')}  "
                            f"[P1:{m.get('portal1_id')} → P2:{m.get('portal2_id')}]\n")

            if templates_created:
                f.write("\n" + "=" * 80 + "\n")
                f.write("CREATED: TEMPLATES\n")
                f.write("=" * 80 + "\n\n")
                for m in sorted(templates_created, key=lambda x: x.get('templateName') or ''):
                    f.write(f"  ✓ {m.get('templateName')}  "
                            f"[P1:{m.get('portal1_id')} → P2:{m.get('portal2_id')}]\n")

            if automations_created:
                f.write("\n" + "=" * 80 + "\n")
                f.write("CREATED: AUTOMATIONS (all in DISABLED state)\n")
                f.write("=" * 80 + "\n\n")
                for m in automations_created:
                    p1 = m.get('portal1') or {}
                    p2 = m.get('portal2') or {}
                    f.write(f"  ✓ {p1.get('automationName', 'Unknown')} (disabled)  "
                            f"[P1:{p1.get('automationId')} → P2:{p2.get('automationId')}]\n")

            if ts_config or categories or activities:
                f.write("\n" + "=" * 80 + "\n")
                f.write("CREATED: TIMESHEETS\n")
                f.write("=" * 80 + "\n\n")
                if ts_config:
                    f.write("  ✓ Timesheet configuration updated\n")
                if categories:
                    f.write(f"\n  Categories ({len(categories)}):\n")
                    for entry in categories.values():
                        f.write(f"    ✓ {(entry.get('portal1') or {}).get('categoryName', 'Unknown')}\n")
                if activities:
                    f.write(f"\n  Activities ({len(activities)}):\n")
                    for entry in activities.values():
                        p1 = entry.get('portal1') or {}
                        f.write(f"    ✓ {p1.get('activityName', 'Unknown')} ({p1.get('type', 'Unknown')})\n")

            f.write("\n" + "=" * 80 + "\n")
            f.write("For items NOT cloned, see: NOT_CLONED.txt\n")
            f.write("For full API detail, see the migration log JSON\n")
            f.write("=" * 80 + "\n")

        print(f"   ✓ Cloned report: CLONED.txt ({total_created} items created)")

    def _save_summary_report(self, migration_dir: str, dry_run: bool):
        """Save summary report as readable text"""
        # Calculate statistics
        fields_mapped = sum(1 for m in self.field_mapping.values() if m.get('matched'))
        fields_created = sum(1 for m in self.field_mapping.values() if not m.get('matched'))

        roles_mapped = sum(1 for m in self.role_mapping.values() if m.get('matched'))
        roles_created = sum(1 for m in self.role_mapping.values() if not m.get('matched'))

        skills_mapped = sum(1 for m in self.skill_mapping.values() if m.get('matched'))
        skills_created = sum(1 for m in self.skill_mapping.values() if not m.get('matched'))

        templates_with_forms = sum(1 for m in self.template_mapping.values() if m.get('has_forms'))

        # Save as readable TXT
        txt_file = os.path.join(migration_dir, "summary.txt")
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("MIGRATION SUMMARY\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Date & Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Mode: {'DRY RUN' if dry_run else 'LIVE MIGRATION'}\n")
            f.write(f"Source Portal: {self.portal1_config['name']}\n")
            f.write(f"Destination Portal: {self.portal2_config['name']}\n")
            f.write("\n" + "=" * 80 + "\n")
            f.write("MIGRATION RESULTS\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"FIELDS: {len(self.field_mapping)} total\n")
            f.write(f"  - Mapped existing: {fields_mapped}\n")
            f.write(f"  - Created new: {fields_created}\n\n")

            f.write(f"ROLES: {len(self.role_mapping)} total\n")
            f.write(f"  - Mapped existing: {roles_mapped}\n")
            f.write(f"  - Created new: {roles_created}\n\n")

            if self.skill_mapping:
                f.write(f"SKILLS: {len(self.skill_mapping)} total\n")
                f.write(f"  - Mapped existing: {skills_mapped}\n")
                f.write(f"  - Created new: {skills_created}\n\n")

            if self.template_mapping:
                f.write(f"TEMPLATES: {len(self.template_mapping)} total\n")
                f.write(f"  - With forms: {templates_with_forms}\n\n")

            if self.automation_mapping:
                f.write(f"AUTOMATIONS: {len(self.automation_mapping)} total\n")
                f.write(f"  - Status: All created in DISABLED state\n\n")

            ts_categories = self.timesheet_mapping.get("categories") or {}
            ts_activities = self.timesheet_mapping.get("activities") or {}
            ts_config = self.timesheet_mapping.get("configuration") or {}
            if ts_config or ts_categories or ts_activities:
                f.write(f"TIMESHEETS: {len(ts_categories) + len(ts_activities) + (1 if ts_config else 0)} total\n")
                f.write(f"  - Configuration: {'updated' if ts_config else 'not migrated'}\n")
                f.write(f"  - Categories: {len(ts_categories)}\n")
                f.write(f"  - Activities: {len(ts_activities)}\n\n")

            if self.created_sections:
                f.write(f"FIELD SECTIONS: {len(self.created_sections)} created\n\n")

            f.write("\n" + "=" * 80 + "\n")
            if self.errors:
                f.write(f"Errors: {len(self.errors)}\n")
                f.write("Check migration_log.json for details\n")
            else:
                f.write("Status: Migration completed successfully with no errors\n")
            f.write("=" * 80 + "\n")

        print(f"   ✓ Summary report: summary.txt")

    def _save_not_cloned_report(self, migration_dir: str, dry_run: bool):
        """Generate report of configurations that were NOT cloned"""
        features = self.migration_config.get('features', {})

        txt_file = os.path.join(migration_dir, "NOT_CLONED.txt")
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("CONFIGURATIONS NOT CLONED\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Date & Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Mode: {'DRY RUN' if dry_run else 'LIVE MIGRATION'}\n")
            f.write(f"Source Portal: {self.portal1_config['name']}\n")
            f.write(f"Destination Portal: {self.portal2_config['name']}\n")
            f.write("\n" + "=" * 80 + "\n")
            f.write("SUMMARY\n")
            f.write("=" * 80 + "\n\n")

            # Track categories
            disabled_items = []
            failed_items = []
            skipped_items = []

            # Check what was disabled
            if not features.get('fields', True):
                disabled_items.append("Fields")
            if not features.get('roles', True):
                disabled_items.append("Roles")
            if not features.get('skills', True):
                disabled_items.append("Skills")
            if not features.get('templates', True):
                disabled_items.append("Templates")
            if not features.get('dependencies', True):
                disabled_items.append("Dependencies")
            if not features.get('automations', False):
                disabled_items.append("Automations")
            if not features.get('timesheets', False):
                disabled_items.append("Timesheets")

            # Analyze errors from migration log
            dependency_500_error = False
            template_failures = []
            automation_failures = []
            field_failures = []
            skill_failures = []
            seen_template = set()
            seen_automation = set()
            seen_field = set()
            seen_skill = set()

            for log_entry in self.migration_log:
                action = log_entry.get('action', '')
                portal = log_entry.get('portal', '')
                response = log_entry.get('response', {})

                # Check if this is a failure
                if not response.get('success', True):
                    status_code = response.get('status_code', 'N/A')
                    error_msg = str(response.get('error', ''))[:200]

                    # Check for dependency API error
                    if action == 'GET_DEPENDENCIES' and '500' in error_msg:
                        dependency_500_error = True

                    # Track template fetch failures
                    if action == 'GET_TEMPLATE_DETAIL' and not response.get('success'):
                        url = log_entry.get('url', '')
                        template_id = url.split('/')[-1] if '/' in url else 'Unknown'
                        if template_id not in seen_template:
                            seen_template.add(template_id)
                            template_failures.append({
                                'portal1_id': template_id,
                                'name': log_entry.get('resource_name', 'Unknown'),
                                'status_code': status_code,
                                'error': error_msg
                            })

                    # Track template create failures
                    if action == 'CREATE_TEMPLATE' and portal == 'Portal 2':
                        request_data = log_entry.get('request_data', {})
                        template_id = log_entry.get('template_id', log_entry.get('resource_id', 'Unknown'))
                        template_name = request_data.get('templateName', log_entry.get('resource_name', 'Unknown'))
                        key = f"{template_id}:{template_name}"
                        if key not in seen_template:
                            seen_template.add(key)
                            template_failures.append({
                                'portal1_id': template_id,
                                'name': template_name,
                                'status_code': status_code,
                                'error': error_msg
                            })

                    # Track automation creation failures
                    if action == 'CREATE_AUTOMATION' and portal == 'Portal 2':
                        request_data = log_entry.get('request_data', {})
                        automation_id = log_entry.get('resource_id', request_data.get('sourceId', 'Unknown'))
                        automation_name = request_data.get('automationName', 'Unknown')
                        key = f"{automation_id}:{automation_name}"
                        if key not in seen_automation:
                            seen_automation.add(key)
                            automation_failures.append({
                                'portal1_id': automation_id,
                                'name': automation_name,
                                'status_code': status_code,
                                'error': error_msg
                            })

                    # Track field creation failures
                    if action == 'CREATE_FIELD' and portal == 'Portal 2':
                        request_data = log_entry.get('request_data', {})
                        field_id = log_entry.get('resource_id', 'Unknown')
                        field_name = request_data.get('fieldLabel', 'Unknown')
                        object_type = request_data.get('objectType', '')
                        key = f"{field_id}:{field_name}:{object_type}"
                        if key not in seen_field:
                            seen_field.add(key)
                            field_failures.append({
                                'portal1_id': field_id,
                                'name': field_name,
                                'objectType': object_type,
                                'status_code': status_code,
                                'error': error_msg
                            })

                    # Track skill creation failures
                    if action == 'CREATE_SKILL' and portal == 'Portal 2':
                        request_data = log_entry.get('request_data', {})
                        skill_id = log_entry.get('resource_id', 'Unknown')
                        skill_name = request_data.get('skillName', request_data.get('fieldLabel', 'Unknown'))
                        key = f"{skill_id}:{skill_name}"
                        if key not in seen_skill:
                            seen_skill.add(key)
                            skill_failures.append({
                                'portal1_id': skill_id,
                                'name': skill_name,
                                'status_code': status_code,
                                'error': error_msg
                            })

            # Write summary counts
            total_not_cloned = len(disabled_items) + len(failed_items)
            if dependency_500_error:
                total_not_cloned += 1
            if template_failures:
                total_not_cloned += 1
            if automation_failures:
                total_not_cloned += 1

            f.write(f"Total Categories Not Cloned: {total_not_cloned}\n")
            f.write(f"  - Disabled by configuration: {len(disabled_items)}\n")
            f.write(f"  - Failed during migration: {len(template_failures) + len(automation_failures) + len(field_failures) + len(skill_failures)}\n")
            f.write(f"  - API errors: {1 if dependency_500_error else 0}\n\n")

            # Disabled items section
            if disabled_items:
                f.write("\n" + "=" * 80 + "\n")
                f.write("DISABLED BY CONFIGURATION\n")
                f.write("=" * 80 + "\n\n")
                f.write("These items were not migrated because they were disabled in the\n")
                f.write("migration configuration (unchecked in Web UI):\n\n")
                for item in disabled_items:
                    f.write(f"  ❌ {item}\n")
                f.write(f"\nTotal: {len(disabled_items)} categories disabled\n")

            # Failed items section — full list with Portal 1 ID, name, status code, error
            if field_failures:
                f.write("\n" + "=" * 80 + "\n")
                f.write("FAILED: FIELDS\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"These {len(field_failures)} fields failed to create:\n\n")
                for field in field_failures:
                    f.write(f"  ❌ [{field['portal1_id']}] {field['name']} ({field.get('objectType','?')}) — HTTP {field['status_code']}\n")
                    if field.get('error'):
                        f.write(f"      Error: {field['error']}\n")
                f.write(f"\nTotal: {len(field_failures)} fields failed\n")

            if skill_failures:
                f.write("\n" + "=" * 80 + "\n")
                f.write("FAILED: SKILLS\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"These {len(skill_failures)} skills failed to create:\n\n")
                for skill in skill_failures:
                    f.write(f"  ❌ [{skill['portal1_id']}] {skill['name']} — HTTP {skill['status_code']}\n")
                    if skill.get('error'):
                        f.write(f"      Error: {skill['error']}\n")
                f.write(f"\nTotal: {len(skill_failures)} skills failed\n")

            if template_failures:
                f.write("\n" + "=" * 80 + "\n")
                f.write("FAILED: TEMPLATES\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"These {len(template_failures)} templates failed to fetch or create:\n\n")
                for template in template_failures:
                    f.write(f"  ❌ [{template['portal1_id']}] {template['name']} — HTTP {template['status_code']}\n")
                    if template.get('error'):
                        f.write(f"      Error: {template['error']}\n")
                f.write(f"\nTotal: {len(template_failures)} templates failed\n")

            if automation_failures:
                f.write("\n" + "=" * 80 + "\n")
                f.write("FAILED: AUTOMATIONS\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"These {len(automation_failures)} automations failed to create:\n\n")
                for automation in automation_failures:
                    f.write(f"  ❌ [{automation['portal1_id']}] {automation['name']} — HTTP {automation['status_code']}\n")
                    if automation.get('error'):
                        f.write(f"      Error: {automation['error']}\n")
                f.write(f"\nTotal: {len(automation_failures)} automations failed\n")
                f.write("\nPossible reasons:\n")
                f.write("  - Missing custom fields (field migration failed first)\n")
                f.write("  - Field ID mismatch (field IDs not remapped correctly)\n")
                f.write("  - Complex validation rules that failed validation\n")
                f.write("  - Budget fields with special permissions\n")

            # API errors section
            if dependency_500_error:
                f.write("\n" + "=" * 80 + "\n")
                f.write("API ERROR: DEPENDENCIES\n")
                f.write("=" * 80 + "\n\n")
                f.write("Status: NOT MIGRATED\n")
                f.write("Error: 500 Server Error from Rocketlane API\n")
                f.write("Endpoint: /api/v1/templates/dependency-map\n\n")
                f.write("Impact: Task and phase dependencies are not configured in destination portal.\n")
                f.write("Templates exist but without their dependency relationships.\n\n")
                f.write("Action Required:\n")
                f.write("  1. Contact Rocketlane Support about dependency-map endpoint\n")
                f.write("  2. Request alternative method to fetch/migrate dependencies\n")
                f.write("  3. Manually recreate critical dependencies as workaround\n")

            # Complete list section (if any category has > 100 items)
            if len(field_failures) > 100 or len(skill_failures) > 100:
                f.write("\n" + "=" * 80 + "\n")
                f.write("COMPLETE LIST OF ALL FAILURES\n")
                f.write("=" * 80 + "\n\n")

                if len(field_failures) > 100:
                    f.write(f"ALL {len(field_failures)} FAILED FIELDS:\n")
                    f.write("-" * 80 + "\n")
                    for i, field in enumerate(field_failures, 1):
                        f.write(f"{i:4d}. {field}\n")
                    f.write("\n")

                if len(skill_failures) > 100:
                    f.write(f"ALL {len(skill_failures)} FAILED SKILLS:\n")
                    f.write("-" * 80 + "\n")
                    for i, skill in enumerate(skill_failures, 1):
                        f.write(f"{i:4d}. {skill}\n")
                    f.write("\n")

            # Known limitations
            f.write("\n" + "=" * 80 + "\n")
            f.write("KNOWN LIMITATIONS (NOT MIGRATED BY DESIGN)\n")
            f.write("=" * 80 + "\n\n")
            f.write("These items are not migrated automatically:\n\n")
            f.write("  ℹ️  Users - Must be added manually to destination portal\n")
            f.write("      Reason: License and permission considerations require manual review\n\n")
            f.write("  ℹ️  User Cost Rates - Not migrated\n")
            f.write("      Requires: Users to exist in destination portal first\n\n")
            f.write("  ℹ️  Holiday Calendars - Not migrated\n")
            f.write("      Requires: Manual setup in destination portal\n\n")

            # Recommendations
            f.write("\n" + "=" * 80 + "\n")
            f.write("RECOMMENDED ACTIONS\n")
            f.write("=" * 80 + "\n\n")

            if field_failures:
                f.write("1. Review field failures in migration_log.json\n")
                f.write("   - Check for missing fieldLabel or validation errors\n")
                f.write("   - Re-run migration after fixing field definitions\n\n")

            if automation_failures:
                f.write("2. Fix automation failures:\n")
                f.write("   - Ensure all custom fields are created first\n")
                f.write("   - Re-run with Fields + Automations selected\n")
                f.write("   - Check for field ID mismatches in automation definitions\n\n")

            if template_failures:
                f.write("3. Handle failed templates:\n")
                f.write("   - Form templates may need manual recreation\n")
                f.write("   - Contact Rocketlane if API support is needed\n\n")

            if dependency_500_error:
                f.write("4. Contact Rocketlane Support:\n")
                f.write("   - Report dependency-map 500 error\n")
                f.write("   - Request alternative migration method\n\n")

            f.write(f"\nFor detailed error messages, check: migration_log.json\n")
            f.write(f"For successfully migrated items, check: summary.txt\n")
            f.write("\n" + "=" * 80 + "\n")

        print(f"   ✓ Not cloned report: NOT_CLONED.txt")

    def load_existing_mappings(self):
        """Load previously saved mapping JSONs from disk into memory.

        Used when re-running templates/automations without re-doing fields/roles.
        Reads field_mapping.json, role_mapping.json, skill_mapping.json from the
        customer directory. Files are expected to have shape: {"mappings": {...}}.
        """
        loaded = []
        targets = [
            ('field_mapping', 'field_mapping'),
            ('role_mapping', 'role_mapping'),
            ('skill_mapping', 'skill_mapping'),
            ('user_mapping', 'user_mapping'),
            ('section_mapping', 'section_mapping'),
        ]
        for config_key, attr_name in targets:
            path = self.logging_config.get(config_key)
            if not path or not os.path.exists(path):
                continue
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                mappings = data.get('mappings', data) if isinstance(data, dict) else {}
                # Skip wrapper meta keys if file is flat
                if isinstance(mappings, dict) and 'migration_timestamp' in mappings:
                    mappings = {k: v for k, v in mappings.items()
                                if k not in ('migration_timestamp', 'total_mappings', 'mappings')}
                setattr(self, attr_name, mappings)
                if isinstance(mappings, dict):
                    self.loaded_mapping_keys[attr_name] = set(mappings.keys())
                loaded.append(f"{attr_name} ({len(mappings)} entries)")
            except Exception as e:
                print(f"   ⚠ Failed to load {path}: {e}")

        if loaded:
            print("\n   Loaded existing mappings from disk:")
            for item in loaded:
                print(f"      ✓ {item}")
        return loaded

    def run_complete_migration(self, dry_run: bool = False):
        """Run complete migration: Fields -> Roles -> Skills -> Templates -> Dependencies -> Automations -> Timesheets"""
        print("=" * 80)
        print("COMPLETE ROCKETLANE MIGRATION - PROPERTIES-BASED")
        print("=" * 80)
        print(f"Source: {self.portal1_config['name']}")
        print(f"Destination: {self.portal2_config['name']}")
        print(f"Mode: {'DRY RUN' if dry_run else 'LIVE MIGRATION'}")
        print(f"Order: Fields → Roles → Skills → Templates → Dependencies → Automations → Timesheets")
        print("=" * 80)

        # Check feature flags
        features = self.migration_config.get('features', {})

        # If load.existing.mappings is set, read saved JSONs from disk into memory
        # so templates/automations can use them without re-running fields/roles steps
        if features.get('load_existing_mappings', False):
            self.load_existing_mappings()

        # Step 1: Migrate Fields
        if features.get('fields', True):
            self.migrate_fields(dry_run)

        # Step 2: Migrate Roles
        if features.get('roles', True):
            self.migrate_roles(dry_run)

        # Step 3: Migrate Skills
        if features.get('skills', True):
            self.migrate_skills(dry_run)

        # Step 4: Migrate Users - DISABLED (user creation not supported)
        # User migration has been disabled - users should be created manually in the destination portal
        # if features.get('users', False):
        #     self.migrate_users(dry_run)

        # Step 5: Migrate Templates
        if features.get('templates', True):
            self.migrate_templates(dry_run)

        # Step 6: Migrate Dependencies
        if features.get('dependencies', True):
            self.migrate_dependencies(dry_run)

        # Step 7: Migrate Automations
        if features.get('automations', False):
            self.migrate_automations(dry_run)

        # Step 8: Migrate Timesheets
        if features.get('timesheets', False):
            self.migrate_timesheets(dry_run)

        # Save all logs
        print("\n" + "=" * 80)
        print("Saving migration logs...")
        self.save_logs()

        # Create detailed migration report
        migration_dir = self.create_migration_report(dry_run)

        print("\n" + "=" * 80)
        print("MIGRATION COMPLETE")
        print("=" * 80)
        print(f"Logs saved:")
        for key, value in self.logging_config.items():
            print(f"  - {value}")
        print(f"\nDetailed reports saved in: {migration_dir}/")
        if self.errors:
            print(f"\n⚠ Errors encountered: {len(self.errors)} (check log files)")
        print("=" * 80)

    def save_logs(self):
        """Save all migration logs and mappings"""
        # Ensure the customer directory exists before writing files
        log_path = self.logging_config['migration_log']
        log_dir = os.path.dirname(log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        # Save migration log
        with open(log_path, 'w') as f:
            json.dump({
                "migration_timestamp": datetime.now().isoformat(),
                "total_operations": len(self.migration_log),
                "errors": len(self.errors),
                "log": self.migration_log
            }, f, indent=2)

        # Save all mappings
        mapping_files = {
            'section_mapping': self.section_mapping,
            'role_mapping': self.role_mapping,
            'skill_mapping': self.skill_mapping,
            'user_mapping': self.user_mapping,
            'template_mapping': self.template_mapping,
            'automation_mapping': self.automation_mapping,
            'timesheet_mapping': self.timesheet_mapping
        }

        for config_key, mapping_data in mapping_files.items():
            filename = self.logging_config.get(config_key)
            if filename:
                with open(filename, 'w') as f:
                    json.dump({
                        "migration_timestamp": datetime.now().isoformat(),
                        "total_mappings": len(mapping_data),
                        "mappings": mapping_data
                    }, f, indent=2)

        # Save field mappings - split by object type for future use
        # This allows running TASK, PROJECT, USER, COMPANY migrations separately
        # and using the mappings together for templates/automations
        if self.field_mapping:
            # Split field mappings by object type
            field_mappings_by_type = {}
            for field_id, field_data in self.field_mapping.items():
                object_type = field_data.get('objectType', 'UNKNOWN')
                if object_type not in field_mappings_by_type:
                    field_mappings_by_type[object_type] = {}
                field_mappings_by_type[object_type][field_id] = field_data

            # Save each object type to its own file, inside the customer directory
            # so per-type mappings don't leak into the working directory and clobber
            # another customer's copies
            customer_dir = self.logging_config.get("customer_directory", "")
            if customer_dir:
                os.makedirs(customer_dir, exist_ok=True)
            for object_type, mappings in field_mappings_by_type.items():
                filename = f"{object_type.lower()}_field_mapping.json"
                if customer_dir:
                    filename = os.path.join(customer_dir, filename)
                with open(filename, 'w') as f:
                    json.dump({
                        "migration_timestamp": datetime.now().isoformat(),
                        "object_type": object_type,
                        "total_mappings": len(mappings),
                        "mappings": mappings
                    }, f, indent=2)
                print(f"   ✓ Saved {object_type} field mappings: {filename}")

            # Also save combined field_mapping.json for backward compatibility
            filename = self.logging_config.get('field_mapping', 'field_mapping.json')
            with open(filename, 'w') as f:
                json.dump({
                    "migration_timestamp": datetime.now().isoformat(),
                    "total_mappings": len(self.field_mapping),
                    "mappings": self.field_mapping
                }, f, indent=2)

        # Save dependency mapping
        with open(self.logging_config['dependency_mapping'], 'w') as f:
            json.dump({
                "migration_timestamp": datetime.now().isoformat(),
                "total_task_mappings": len(self.task_id_mapping),
                "total_phase_mappings": len(self.phase_id_mapping),
                "task_id_mapping": self.task_id_mapping,
                "phase_id_mapping": self.phase_id_mapping
            }, f, indent=2)


def main():
    """Main entry point"""
    import sys

    # Allow specifying a different properties file
    properties_file = "portal.properties"
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        if idx + 1 < len(sys.argv):
            properties_file = sys.argv[idx + 1]

    migrator = CompleteMigratorWithProperties(properties_file)
    dry_run = "--dry-run" in sys.argv or "-d" in sys.argv

    migrator.run_complete_migration(dry_run=dry_run)


if __name__ == "__main__":
    main()
