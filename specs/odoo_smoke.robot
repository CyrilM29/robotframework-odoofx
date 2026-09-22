*** Settings ***
Documentation     ODOOFX Smoke Test Suite
...               Verifies basic Odoo connectivity and navigation.
...               Credentials come from the command line, never from this file:
...               robot -v PASSWORD:<secret> specs/odoo_smoke.robot

Library           OdooFxLibrary

*** Variables ***
${ODOO_URL}       http://localhost:8069
${USER_EMAIL}     admin@example.com
${PASSWORD}       ${EMPTY}

*** Test Cases ***
Smoke Test : Connect to Odoo
    [Documentation]    Verify that we can connect to an Odoo instance
    [Tags]            smoke    bootstrap
    Connect To Odoo    ${ODOO_URL}    ${USER_EMAIL}    ${PASSWORD}

Smoke Test : Navigate to Sales Menu
    [Documentation]    Verify that we can navigate to the Sales menu
    [Tags]            smoke    bootstrap
    Connect To Odoo    ${ODOO_URL}    ${USER_EMAIL}    ${PASSWORD}
    Navigate To Menu    Sales
    Disconnect From Odoo

*** Keywords ***
# Additional keywords will be added here as the suite grows
