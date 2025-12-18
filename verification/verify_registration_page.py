from playwright.sync_api import sync_playwright

def verify_registration_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate to Official Register page
        # Assuming port 5000 as per usual Flask default
        page.goto("http://localhost:5000/official/register")

        # Click "Siguiente" to go to Step 2 where the bank account field is
        # The form has steps hidden via JS.
        # Step 1 inputs: First Name, Last Name
        page.get_by_placeholder("Nombre").fill("Test")
        page.get_by_placeholder("Apellido").fill("Officer")
        page.get_by_role("button", name="Siguiente").click()

        # Now on Step 2
        # Check for DNI and Account Number
        page.wait_for_selector('input[placeholder="Número de Cuenta Bancaria"]')

        # Take screenshot of Step 2
        page.screenshot(path="verification/official_register_step2.png")

        browser.close()

if __name__ == "__main__":
    verify_registration_page()
