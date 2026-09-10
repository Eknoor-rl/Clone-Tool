"""
Properties File Loader for Rocketlane Migration
Reads portal.properties file and converts to Python configuration
"""

import os
from typing import Dict, Any, List


class PropertiesLoader:
    """Load and parse properties file"""

    def __init__(self, properties_file: str = "portal.properties"):
        self.properties_file = properties_file
        self.properties = {}
        self._load_properties()

    def _load_properties(self):
        """Load properties from file"""
        if not os.path.exists(self.properties_file):
            raise FileNotFoundError(f"Properties file not found: {self.properties_file}")

        with open(self.properties_file, 'r') as f:
            for line in f:
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue

                # Parse key=value
                if '=' in line:
                    key, value = line.split('=', 1)
                    self.properties[key.strip()] = value.strip()

    def get(self, key: str, default: Any = None) -> Any:
        """Get property value"""
        return self.properties.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        """Get property as integer"""
        value = self.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get property as float"""
        value = self.get(key)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get property as boolean"""
        value = self.get(key)
        if value is None:
            return default
        return value.lower() in ('true', 'yes', '1', 'on')

    def get_list(self, key: str, delimiter: str = ',', default: List = None) -> List[str]:
        """Get property as list"""
        value = self.get(key)
        if value is None:
            return default or []
        return [item.strip() for item in value.split(delimiter) if item.strip()]

    def get_portal1_config(self) -> Dict[str, Any]:
        """Get Portal 1 configuration as dictionary"""
        return {
            "name": self.get("portal1.name"),
            "base_url": self.get("portal1.base.url"),
            "api_base": self.get("portal1.api.base"),
            "v1_api_base": self.get("portal1.v1.api.base"),
            "api_key": self.get("portal1.api.key"),
            "automation_api_key": self.get("portal1.automation.api.key"),
            "account_id": self.get_int("portal1.account.id"),
            "endpoints": {
                "fields": self.get("portal1.endpoint.fields"),
                "field_detail": self.get("portal1.endpoint.field.detail"),
                "all_fields": self.get("portal1.endpoint.all.fields"),
                "field_sections": self.get("portal1.endpoint.field.sections"),
                "roles": self.get("portal1.endpoint.roles"),
                "skills": self.get("portal1.endpoint.skills"),
                "users": self.get("portal1.endpoint.users"),
                "cost_rates": self.get("portal1.endpoint.cost.rates"),
                "holiday_calendar": self.get("portal1.endpoint.holiday.calendar"),
                "templates": self.get("portal1.endpoint.templates"),
                "template_detail": self.get("portal1.endpoint.template.detail"),
                "template_dependencies": self.get("portal1.endpoint.template.dependencies"),
                "automations_global": self.get("portal1.endpoint.automations.global"),
                "timesheets_configuration": self.get("portal1.endpoint.timesheets.configuration"),
                "timesheets_categories": self.get("portal1.endpoint.timesheets.categories"),
                "timesheets_activity": self.get("portal1.endpoint.timesheets.activity")
            },
            "sample_user": {
                "userId": self.get_int("portal1.sample.user.id"),
                "emailId": self.get("portal1.sample.user.email"),
                "userName": self.get("portal1.sample.user.name"),
                "firstName": self.get("portal1.sample.user.first.name"),
                "lastName": self.get("portal1.sample.user.last.name"),
                "userType": self.get("portal1.sample.user.type")
            }
        }

    def get_portal2_config(self) -> Dict[str, Any]:
        """Get Portal 2 configuration as dictionary"""
        return {
            "name": self.get("portal2.name"),
            "base_url": self.get("portal2.base.url"),
            "api_base": self.get("portal2.api.base"),
            "api_key": self.get("portal2.api.key"),
            "endpoints": {
                "fields": self.get("portal2.endpoint.fields"),
                "field_sections": self.get("portal2.endpoint.field.sections"),
                "roles": self.get("portal2.endpoint.roles"),
                "skills": self.get("portal2.endpoint.skills"),
                "users": self.get("portal2.endpoint.users"),
                "cost_rates": self.get("portal2.endpoint.cost.rates"),
                "templates": self.get("portal2.endpoint.templates"),
                "template_detail": self.get("portal2.endpoint.template.detail"),
                "template_dependencies": self.get("portal2.endpoint.template.dependencies"),
                "automations_global": self.get("portal2.endpoint.automations.global"),
                "timesheets_configuration": self.get("portal2.endpoint.timesheets.configuration"),
                "timesheets_categories": self.get("portal2.endpoint.timesheets.categories"),
                "timesheets_activity": self.get("portal2.endpoint.timesheets.activity")
            }
        }

    def get_migration_config(self) -> Dict[str, Any]:
        """Get migration configuration"""
        return {
            "choice_field_types": self.get_list("migration.choice.field.types"),
            "object_types": self.get_list("migration.object.types"),
            "excluded_field_ids": self.get_list("migration.excluded.field.ids"),
            "template_order": self.get_list("migration.template.order"),
            "template_object_type": self.get("migration.template.object.type", "PROJECT"),
            "features": {
                "fields": self.get_bool("migration.enable.fields", True),
                "fields_task": self.get_bool("migration.enable.fields.task", True),
                "fields_project": self.get_bool("migration.enable.fields.project", True),
                "fields_user": self.get_bool("migration.enable.fields.user", True),
                "fields_company": self.get_bool("migration.enable.fields.company", True),
                "roles": self.get_bool("migration.enable.roles", True),
                "skills": self.get_bool("migration.enable.skills", True),
                "users": self.get_bool("migration.enable.users", True),
                "templates": self.get_bool("migration.enable.templates", True),
                "dependencies": self.get_bool("migration.enable.dependencies", True),
                "automations": self.get_bool("migration.enable.automations", False),
                "timesheets": self.get_bool("migration.enable.timesheets", False),
                "load_existing_mappings": self.get_bool("migration.load.existing.mappings", False)
            }
        }

    def get_logging_config(self) -> Dict[str, str]:
        """Get logging configuration"""
        return {
            "customer_directory": self.get("customer.directory", "customers/default"),
            "migration_log": self.get("logging.migration.log"),
            "field_mapping": self.get("logging.field.mapping"),
            "section_mapping": self.get("logging.section.mapping"),
            "role_mapping": self.get("logging.role.mapping"),
            "skill_mapping": self.get("logging.skill.mapping"),
            "user_mapping": self.get("logging.user.mapping"),
            "template_mapping": self.get("logging.template.mapping"),
            "dependency_mapping": self.get("logging.dependency.mapping"),
            "automation_mapping": self.get("logging.automation.mapping"),
            "timesheet_mapping": self.get("logging.timesheet.mapping")
        }

    def get_rate_limits(self) -> Dict[str, float]:
        """Get rate limiting configuration"""
        return {
            "field_detail_fetch": self.get_float("ratelimit.field.detail.fetch", 0.1),
            "field_creation": self.get_float("ratelimit.field.creation", 0.2),
            "field_option_add": self.get_float("ratelimit.field.option.add", 0.1),
            "role_creation": self.get_float("ratelimit.role.creation", 0.2),
            "skill_creation": self.get_float("ratelimit.skill.creation", 0.2),
            "user_creation": self.get_float("ratelimit.user.creation", 0.3),
            "template_creation": self.get_float("ratelimit.template.creation", 0.2),
            "template_detail_fetch": self.get_float("ratelimit.template.detail.fetch", 0.1),
            "automation_creation": self.get_float("ratelimit.automation.creation", 0.2),
            "timesheet_creation": self.get_float("ratelimit.timesheet.creation", 0.2)
        }

    def get_all_config(self) -> Dict[str, Any]:
        """Get complete configuration"""
        return {
            "portal1": self.get_portal1_config(),
            "portal2": self.get_portal2_config(),
            "migration": self.get_migration_config(),
            "logging": self.get_logging_config(),
            "rate_limits": self.get_rate_limits()
        }

    def export_to_python_config(self, output_file: str = "config_from_properties.py"):
        """Export properties to Python config file format"""
        config = self.get_all_config()

        with open(output_file, 'w') as f:
            f.write('"""\n')
            f.write('Configuration generated from portal.properties\n')
            f.write('"""\n\n')

            # Portal 1
            f.write("# Portal 1 Configuration\n")
            f.write(f"PORTAL_1 = {repr(config['portal1'])}\n\n")

            # Portal 2
            f.write("# Portal 2 Configuration\n")
            f.write(f"PORTAL_2 = {repr(config['portal2'])}\n\n")

            # Migration Config
            migration = config['migration']
            f.write("# Migration Configuration\n")
            f.write(f"CHOICE_FIELD_TYPES = {migration['choice_field_types']}\n")
            f.write(f"OBJECT_TYPES = {migration['object_types']}\n")
            f.write(f"EXCLUDED_FIELD_IDS = {migration['excluded_field_ids']}\n")
            f.write(f"TEMPLATE_ORDER = {migration['template_order']}\n")
            f.write(f"MIGRATION_FEATURES = {repr(migration['features'])}\n\n")

            # Logging Config
            logging = config['logging']
            f.write("# Logging Configuration\n")
            f.write(f"LOG_FILE = {repr(logging['migration_log'])}\n")
            f.write(f"MAPPING_FILE = {repr(logging['field_mapping'])}\n")
            f.write(f"ROLE_MAPPING_FILE = {repr(logging['role_mapping'])}\n")
            f.write(f"SKILL_MAPPING_FILE = {repr(logging['skill_mapping'])}\n")
            f.write(f"USER_MAPPING_FILE = {repr(logging['user_mapping'])}\n")
            f.write(f"TEMPLATE_MAPPING_FILE = {repr(logging['template_mapping'])}\n")
            f.write(f"DEPENDENCY_MAPPING_FILE = {repr(logging['dependency_mapping'])}\n")
            f.write(f"AUTOMATION_MAPPING_FILE = {repr(logging['automation_mapping'])}\n\n")

            # Rate Limits
            f.write("# Rate Limits\n")
            f.write(f"RATE_LIMITS = {repr(config['rate_limits'])}\n")

        print(f"✓ Exported configuration to {output_file}")


def main():
    """Example usage and testing"""
    print("Loading properties from portal.properties...")

    try:
        loader = PropertiesLoader()

        print("\n" + "=" * 60)
        print("PORTAL 1 CONFIGURATION")
        print("=" * 60)
        portal1 = loader.get_portal1_config()
        print(f"Name: {portal1['name']}")
        print(f"Base URL: {portal1['base_url']}")
        print(f"API Key: {portal1['api_key'][:20]}...")
        print(f"Account ID: {portal1['account_id']}")

        print("\n" + "=" * 60)
        print("PORTAL 2 CONFIGURATION")
        print("=" * 60)
        portal2 = loader.get_portal2_config()
        print(f"Name: {portal2['name']}")
        print(f"Base URL: {portal2['base_url']}")
        print(f"API Key: {portal2['api_key'][:20]}...")

        print("\n" + "=" * 60)
        print("MIGRATION CONFIGURATION")
        print("=" * 60)
        migration = loader.get_migration_config()
        print(f"Object Types: {migration['object_types']}")
        print(f"Template Order: {migration['template_order']}")
        print(f"Features: {migration['features']}")

        print("\n" + "=" * 60)
        print("RATE LIMITS")
        print("=" * 60)
        rate_limits = loader.get_rate_limits()
        for key, value in rate_limits.items():
            print(f"  {key}: {value}s")

        # Export to Python config
        print("\n" + "=" * 60)
        loader.export_to_python_config()

    except FileNotFoundError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Error loading properties: {e}")


if __name__ == "__main__":
    main()
