# Connecting Microsoft (Outlook and Microsoft 365)

Life OS reads and sends mail through Microsoft Graph. Each inbox you connect is one card in Brain, Sources, and one mail account; you can connect any number, beside Gmail. Mail is searched live and never copied. The Azure app's client ID and secret are kept in the site config, never in the repository.

## 1. Register an app in Azure

1. Sign in to https://entra.microsoft.com (or portal.azure.com, Microsoft Entra ID) and open **App registrations**, **New registration**.
2. Name it (for example Life OS). **Supported account types**: choose "Accounts in any organizational directory and personal Microsoft accounts" to connect work and personal inboxes; choose a single directory to allow only your own organisation.
3. **Redirect URI**: type **Web**, and the address Life OS shows. Open Brain, Sources, **Connect Microsoft**: the dialog prints the redirect address for the next inbox when sign-in is set up, otherwise build it from your site: `https://YOUR-SITE/api/method/frappe.integrations.doctype.connected_app.connected_app.callback/life-os-microsoft-1`. Each further inbox uses the next number (`life-os-microsoft-2`, `-3`, ...): add each address to the registration before connecting that inbox.
4. **API permissions**, Microsoft Graph, **Delegated**: `offline_access` (a refresh token, so you stay signed in), `User.Read` (the inbox's address), `Mail.Read` (search and read), `Mail.ReadWrite` (drafts, archive and categories) and `Mail.Send` (send). Work and school tenants may need an administrator to grant consent.
5. **Certificates and secrets**, **New client secret**. Copy the secret's **Value** now: Azure shows it once.

## 2. Give the keys to the site

On the bench (never in a file in the repository, an issue or a pull request):

```
bench --site YOUR-SITE set-config lifeos_microsoft_client_id "THE-APPLICATION-CLIENT-ID"
bench --site YOUR-SITE set-config lifeos_microsoft_client_secret "THE-SECRET-VALUE"
bench --site YOUR-SITE set-config lifeos_microsoft_tenant "common"
```

`lifeos_microsoft_tenant` is `common` (work, school and personal accounts) unless you registered the app for one directory only: then use that directory's ID, or `organizations` / `consumers`. The two keys are the only secrets; the sign-in token of each inbox is kept encrypted by Frappe (Token Cache).

## 3. Connect an inbox

Brain, Sources, **Connect Microsoft**, **Continue to Microsoft**, sign in, accept. Life OS brings you back, reads the inbox's address and switches the card on. Repeat for another inbox. **Remove this mailbox** (the card's settings) forgets the sign-in; what was filed from it stays.

## What it does

- Ask and your agent search the inbox live, with the same plain fields as for Gmail; `raw` is a Graph search string (KQL, for example `participants:anil`).
- The daily digest lists the mail from real people, by inbox, Gmail and Microsoft together.
- Send and draft (a reply sits in its conversation), archive (moves the conversation to Archive) and label (an Outlook category) follow the same switches and approvals as for Google. There is no delete.
- A thread is an Outlook conversation. Microsoft's calendar is not connected: the calendar tools use a Google inbox.
