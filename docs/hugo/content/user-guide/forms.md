---
title: "Forms"
weight: 5
---

# Forms

open-packet supports structured form messages — ICS (Incident Command System) forms and other standard amateur radio forms used in emergency and served agency communication.

## What Are Form Messages?

Form messages are structured messages where the content follows a defined template with named fields (e.g. incident name, date/time, location). They are used in EMCOMM and ARES/RACES operations to ensure consistent, machine-readable traffic.

## Opening the Form Picker

Press **F** to open the form picker. You'll see a list of available form categories and forms.

Navigate the form categories and select a form to fill out.

![Form picker screenshot](../images/screenshot-form-picker.png)

## Filling Out a Form

Once you select a form, the form fill screen opens. Each field in the form is presented as an input:

- Use **Tab** and **Shift+Tab** to navigate between fields
- Enter values in each field
- Fields marked as required must be filled before the form can be sent

Press **Ctrl+S** when the form is complete to compose the message using the form's output template.

The composed message will be addressed and queued for sending on the next sync (**Ctrl+C**).

![Form fill screenshot](../images/screenshot-form-fill.png)

## Updating Default Forms

The default form library is maintained in the open-packet repository. To check for updated form definitions:

{{< hint info >}}
The "Update Default Forms" command in the command palette checks the `main` branch of the repository for new or updated form definitions and downloads them to your local installation.
{{< /hint >}}

## Form Library Location

Form definitions are stored in YAML format in the `forms/` directory of the open-packet package. Each form specifies:
- Field names, types, and validation rules
- The output format template used to generate the message body
