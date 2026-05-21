"""
Direct unit test runner using Python's built-in modules.
"""
import os
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from tests.test_email_service import test_email_service_empty, test_build_html_body, test_send_articles_set_fallback

if __name__ == "__main__":
    print("Running EmailService Tests...")
    try:
        print("- Testing empty article set...", end=" ")
        test_email_service_empty()
        print("PASSED")
        
        print("- Testing HTML body builder...", end=" ")
        test_build_html_body()
        print("PASSED")
        
        print("- Testing SMTP fallback local saving...", end=" ")
        test_send_articles_set_fallback()
        print("PASSED")
        
        print("\nAll EmailService tests passed successfully!")
        sys.exit(0)
    except Exception as e:
        print("\nTEST FAILED!")
        import traceback
        traceback.print_exc()
        sys.exit(1)
