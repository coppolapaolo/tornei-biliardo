#!/usr/bin/env python3
"""
Script to automatically fix common test issues after analyzing specifications alignment.

This script fixes:
1. Notification enum usage
2. Missing required fields
3. Deprecated attributes
"""

import os
import re
import glob


def fix_notification_tests():
    """Fix notification test files with common patterns."""

    # Find all test files that use notifications
    test_files = glob.glob("tests/new/**/*notification*.py", recursive=True)
    test_files.extend(glob.glob("tests/new/**/*test*.py", recursive=True))

    for filepath in test_files:
        if not os.path.exists(filepath):
            continue

        print(f"Processing {filepath}...")

        with open(filepath, "r") as f:
            content = f.read()

        original_content = content

        # Fix import statements
        if "from models import User, Notification" in content:
            if "from models.notification.models import NotificationType" not in content:
                content = content.replace(
                    "from models import User, Notification",
                    """from models import User, Notification
from models.notification.models import NotificationType, NotificationStatus""",
                )

        # Fix notification_type string values to enum
        content = re.sub(
            r"notification_type=[\"\']info[\"\']",
            "notification_type=NotificationType.SYSTEM_ANNOUNCEMENT",
            content,
        )

        content = re.sub(
            r"notification_type=[\"\']system_announcement[\"\']",
            "notification_type=NotificationType.SYSTEM_ANNOUNCEMENT",
            content,
        )

        content = re.sub(
            r"notification_type=[\"\']match_proposal[\"\']",
            "notification_type=NotificationType.MATCH_PROPOSAL",
            content,
        )

        # Fix is_read usages
        content = re.sub(
            r"assert notification\.is_read is False",
            "assert notification.status == NotificationStatus.PENDING",
            content,
        )

        content = re.sub(
            r"assert notification\.is_read is True",
            "assert notification.status == NotificationStatus.READ",
            content,
        )

        content = re.sub(r"is_read=True", "status=NotificationStatus.READ", content)

        content = re.sub(r"is_read=False", "status=NotificationStatus.PENDING", content)

        # Fix Notification constructor calls missing notification_type
        content = re.sub(
            r"Notification\(\s*user_id=([^,]+),\s*title=([^,]+),\s*message=([^,\)]+)\s*\)",
            r"Notification(user_id=\1, title=\2, message=\3, notification_type=NotificationType.SYSTEM_ANNOUNCEMENT)",
            content,
        )

        # Fix assertion comparisons
        content = re.sub(
            r"== [\"\']info[\"\']", "== NotificationType.SYSTEM_ANNOUNCEMENT", content
        )

        content = re.sub(
            r"== [\"\']system_announcement[\"\']",
            "== NotificationType.SYSTEM_ANNOUNCEMENT",
            content,
        )

        # Only write if content changed
        if content != original_content:
            with open(filepath, "w") as f:
                f.write(content)
            print(f"  ✅ Fixed {filepath}")
        else:
            print(f"  ⚪ No changes needed in {filepath}")


def fix_user_tests():
    """Fix user test files with common patterns."""
    test_files = glob.glob("tests/new/**/*user*.py", recursive=True)
    test_files.extend(glob.glob("tests/new/**/*auth*.py", recursive=True))

    for filepath in test_files:
        if not os.path.exists(filepath):
            continue

        print(f"Processing {filepath}...")

        with open(filepath, "r") as f:
            content = f.read()

        original_content = content

        # Fix enum imports if missing
        if (
            "UserRole.ADMIN" in content
            and "from models.user.role_enum import UserRole" not in content
        ):
            content = content.replace(
                "from models import",
                "from models.user.role_enum import UserRole\nfrom models import",
            )

        # Only write if content changed
        if content != original_content:
            with open(filepath, "w") as f:
                f.write(content)
            print(f"  ✅ Fixed {filepath}")


def fix_missing_service_imports():
    """Fix missing service imports."""
    test_files = glob.glob("tests/new/**/*.py", recursive=True)

    for filepath in test_files:
        if not os.path.exists(filepath):
            continue

        with open(filepath, "r") as f:
            content = f.read()

        original_content = content

        # Fix common missing imports
        if "CampionatoService" in content and "TournamentService" not in content:
            content = content.replace("CampionatoService", "TournamentService()")

        if "DirectorRequestService" in content:
            if "from models.user.services import DirectorRequestService" not in content:
                # Add import at the top
                lines = content.split("\n")
                import_line = "from models.user.services import DirectorRequestService"
                if import_line not in content:
                    # Find where to insert the import
                    insert_pos = 0
                    for i, line in enumerate(lines):
                        if line.startswith("from models") or line.startswith("import"):
                            insert_pos = i + 1
                        elif line.strip() == "" and insert_pos > 0:
                            break
                    lines.insert(insert_pos, import_line)
                    content = "\n".join(lines)

        # Only write if content changed
        if content != original_content:
            with open(filepath, "w") as f:
                f.write(content)
            print(f"  ✅ Fixed {filepath}")


if __name__ == "__main__":
    print("🔧 Automatically fixing test issues...")

    print("\n1. Fixing notification tests...")
    fix_notification_tests()

    print("\n2. Fixing user tests...")
    fix_user_tests()

    print("\n3. Fixing missing service imports...")
    fix_missing_service_imports()

    print("\n✅ Test fixing completed!")
    print("Run tests again to see improvements.")
