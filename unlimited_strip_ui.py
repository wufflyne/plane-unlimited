"""
plane-unlimited: build-time patches to the prebuilt Plane assets.

Run at image build time (RUN python3 /tmp/unlimited_strip_ui.py):

  1. web help menu: hide the "Contact Sales" (mailto) and sidebar
     "Contact sales" (plane.so) entries by dead-coding their JSX.
  2. god-mode General settings: hide the whole "Chat + telemetry"
     section (telemetry + cloud-chat toggles) and trim the page
     description; the instance-name form keeps working.
  3. RabbitMQ 4.x compatibility: drop the live-exporter queue arg
     RabbitMQ 4 rejects, and give the Node amqplib programs
     frameMax=8192 via supervisor env substitution.

Every replacement is asserted to match exactly once, so a renamed
upstream asset fails the build loudly instead of silently shipping
the upsell UI or a crash-looping service.

Author: wufflyne <wufflyne@proton.me> — wufflyne.com
"""


def patch(path, subs):
    """Apply (old, new) replacements; each must match exactly once."""
    with open(path, "r", encoding="utf-8") as fh:
        data = fh.read()
    for old, new in subs:
        found = data.count(old)
        assert found == 1, "%s: expected 1 occurrence of %r, found %d" % (path, old[:60], found)
        data = data.replace(old, new)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data)


# --- 1a. web help menu: hide the "Contact Sales" mailto entry ----------------
patch(
    "/app/web/assets/page-BSrFdSJX.js",
    [
        (
            "{title:`Contact Sales`,icon:ve,",
            "{title:`Contact Sales`,shouldRender:!1,icon:ve,",
        )
    ],
)

# --- 1b. web sidebar help popover: hide the "Contact sales" entry -----------
patch(
    "/app/web/assets/navigation-Da_Sv0y9.js",
    [
        (
            "(0,Y.jsx)(A,{icon:(0,Y.jsx)(O,{icon:St,tint:`secondary`}),"
            "label:e(`contact_sales`)",
            "!1&&(0,Y.jsx)(A,{icon:(0,Y.jsx)(O,{icon:St,tint:`secondary`}),"
            "label:e(`contact_sales`)",
        )
    ],
)

# --- 2. god-mode General settings: hide the "Chat + telemetry" section -----
patch(
    "/app/admin/assets/page-BLBrxS83.js",
    [
        # prefix the section root jsx with !1&& so React renders nothing
        (
            "(0,b.jsxs)(`div`,{className:`space-y-6`,children:[(0,b.jsx)(`div`,{"
            "className:`text-body-md-medium text-primary pb-1.5 border-b border-subtle`,"
            "children:`Chat + telemetry`}",
            "!1&&(0,b.jsxs)(`div`,{className:`space-y-6`,children:[(0,b.jsx)(`div`,{"
            "className:`text-body-md-medium text-primary pb-1.5 border-b border-subtle`,"
            "children:`Chat + telemetry`}",
        ),
        # drop the telemetry mention from the page description
        (
            "Change the name of your instance and instance admin e-mail addresses."
            " Enable or disable telemetry in your instance.",
            "Change the name of your instance and instance admin e-mail addresses.",
        ),
    ],
)

# --- 3a. live-exporter: drop the queue arg RabbitMQ 4.x rejects --------------
patch(
    "/app/live/apps/live/dist/start.mjs",
    [
        (
            '\t\t\t\t"x-dead-letter-routing-key": cfg.dlx.routingKey,\n'
            '\t\t\t\t"x-consumer-timeout": env.EXPORT_CONSUMER_TIMEOUT_MS\n',
            '\t\t\t\t"x-dead-letter-routing-key": cfg.dlx.routingKey\n',
        )
    ],
)

# --- 3b. Node amqplib programs need frameMax=8192 for RabbitMQ 4.x ---------
# amqplib defaults to frameMax=4096, which RabbitMQ 4.x rejects at connection
# negotiation (ECONNRESET loops). Python kombu does not accept a frameMax=
# query param in AMQP_URL, so add the query only for the Node programs via
# supervisor %(ENV_AMQP_URL)s substitution, keeping AMQP_URL itself clean.
patch(
    "/app/supervisor.conf",
    [
        # [program:live]
        (
            "environment=PORT=3005,HOSTNAME=0.0.0.0\n",
            'environment=PORT=3005,HOSTNAME=0.0.0.0,AMQP_URL="%(ENV_AMQP_URL)s?frameMax=8192"\n',
        ),
        # [program:live-exporter]
        (
            "environment=LIVE_MODE=exporter\n",
            'environment=LIVE_MODE=exporter,AMQP_URL="%(ENV_AMQP_URL)s?frameMax=8192"\n',
        ),
        # [program:silo]
        (
            "environment=PORT=3006,HOSTNAME=0.0.0.0,API_INTERNAL_BASE_URL=http://localhost:3004\n",
            "environment=PORT=3006,HOSTNAME=0.0.0.0,"
            'API_INTERNAL_BASE_URL=http://localhost:3004,AMQP_URL="%(ENV_AMQP_URL)s?frameMax=8192"\n',
        ),
    ],
)

print("plane-unlimited: UI stripping applied (Contact Sales, Chat + telemetry section)")
print("plane-unlimited: live-exporter x-consumer-timeout arg removed for RabbitMQ 4.x")
print("plane-unlimited: silo/live/live-exporter AMQP_URL got ?frameMax=8192 for RabbitMQ 4.x")
