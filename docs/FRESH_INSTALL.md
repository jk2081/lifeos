# Reinstalling the live site fresh

The owner decided on 20 November 2026 that the live site's data does not need to be kept. So instead of migrating it, the site is wiped and installed fresh **once**, when the new UI is in. That means after the phase 2 issues are merged, including #44 to #50. Until then, use the live site lightly: everything on it will be lost.

Everything below runs on the server as the `frappe` user, in `~/frappe-bench`. Passwords are typed at the prompts, never on the command line and never in chat.

## Before you start

- Note what you will need to reconnect: the Google client ID and secret (in your Google Cloud project), and the Hermes profile that uses Life OS.
- Optional: keep a last backup, in case you want to look something up later.

```
cd ~/frappe-bench
bench --site life.jaikejriwal.com backup --with-files
```

## 1. Update the code

```
cd ~/frappe-bench/apps/lifeos && git pull
cd ~/frappe-bench && bench setup requirements && bench build --app lifeos
```

## 2. Drop the old site and create it again

```
bench drop-site life.jaikejriwal.com          # asks for the MariaDB root password; moves the site to archived_sites
bench new-site life.jaikejriwal.com           # asks for the MariaDB root password and a new Administrator password
bench --site life.jaikejriwal.com install-app lifeos
bench --site life.jaikejriwal.com enable-scheduler
```

The site name stays the same, so nginx and the certificate keep working. Run `sudo bench setup nginx` and `sudo service nginx reload` only if the site does not load.

## 3. Make yourself the owner

Once #49 is merged:

```
bench --site life.jaikejriwal.com execute lifeos.install.new_owner --kwargs "{'email': 'jai.kejriwal@rungamattee.com', 'full_name': 'Jai Kejriwal'}"
```

Then set your password from the reset link Frappe sends, or as Administrator in the browser. Before #49, create the user in the browser as Administrator and run:

```
bench --site life.jaikejriwal.com execute lifeos.install.set_owner --kwargs "{'user': 'jai.kejriwal@rungamattee.com'}"
```

Do not load the seed or demo data. Open `/life` and go through the first-run guide (#49).

## 4. Reconnect

- **Google Calendar:** in Life OS, open Settings → Calendar and enter the client ID and secret, then connect. The redirect address registered in Google stays the same. If calls to Google hang, the IPv4 preference in `/etc/gai.conf` from the first install is still in place; nothing to redo.
- **Agents (Hermes, Claude):**
  1. Create their users with the Life Agent role, and add them in Settings → Members.
  2. Generate a new API key and secret for each, and enter them in Hermes's own config on the server. They never go in chat.
  3. Point Hermes at the skills Life OS serves (`lifeos.api.skills.get`, named `lifeos` and `lifeos-file-work`).
- **The AI key** for Ask and the built-in Brain: Settings → Advanced, or `bench --site life.jaikejriwal.com set-config anthropic_api_key` typed at the server, never in chat.

## 5. Check

```
bench --site life.jaikejriwal.com doctor
```

Then open Today, Brain, Goals and Library, capture one thing from the phone, and check that Hermes can file one thing.

## Later updates

After the fresh install, updates are in place: pull, `bench --site life.jaikejriwal.com migrate`, build, restart. Take a backup first. bench_updater (#2) will do this from the app later.
