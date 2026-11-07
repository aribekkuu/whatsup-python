# Terminal Group Chat

A multi-user chat that runs in the terminal, built with plain Python sockets and threads — no third-party packages.

You start the server and chat from its console as the host. Everyone else joins with a single command (`nc` or `openssl`) — they don't need Python, this code, or any app installed.

```
[19:45] *** dauren joined the chat
[19:45] dauren: salam
[19:46] aru: hi everyone
alibek: █
```

## Features

- **Full-duplex chat** — messages appear instantly, even while you're typing. Incoming lines are inserted *above* your input line, so what you've typed is never lost.
- **Group chat** — any number of participants, one thread per client.
- **Commands** — `/who`, `/msg` (private messages), `/kick` (host only), `/help`.
- **Timestamps** on every message — `[17:45] dauren: hi`.
- **Colored nicknames** — each participant gets their own color.
- **Password protection** — optional; 3 attempts with a delay between them to slow down brute force.
- **TLS encryption** (`--ssl`) — participants connect with the built-in `openssl` client, so traffic and the password aren't sent in plain text.
- **Input sanitizing** — control characters are stripped from names and messages, so nobody can clear other people's screens or forge messages with ANSI escape codes.
- **Unique names** — taken, empty, or space-containing names are rejected.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (or plain `python3`)
- Participants: `nc` or `openssl` — both are preinstalled on macOS and Linux

## Quick start (same Wi-Fi)

```bash
uv run group-chat-v3.py
```

Enter your name and an optional password. Find your local IP:

```bash
ipconfig getifaddr en0      # macOS
hostname -I                 # Linux
```

Participants on the same network join with:

```bash
nc <ip> <port>
```

## Encrypted mode (`--ssl`)

Create a self-signed certificate once, in the same folder as the script:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 365 -subj "/CN=chat"
```

Start the server:

```bash
uv run group-chat-v3.py --ssl
```

Participants join with:

```bash
openssl s_client -quiet -connect <host>:33000
```

A `self signed certificate` warning on connect is expected — the connection is still encrypted. Plain `nc` won't work in this mode.

Custom certificate paths: `--cert path/to/cert.pem --key path/to/key.pem`.

> Don't commit `key.pem` — add `*.pem` to `.gitignore`.

## Chatting over the internet

Your laptop's `192.168.x.x` address is only reachable inside your home network. To let friends in other cities join without installing anything, open a tunnel with [bore](https://github.com/ekzhang/bore):

```bash
brew install bore-cli
uv run group-chat-v3.py --ssl          # terminal 1
bore local 33000 --to bore.pub         # terminal 2
```

bore prints something like `listening at bore.pub:12736`. Send your friend the command and the password (separately):

```bash
openssl s_client -quiet -connect bore.pub:12736
```

The port changes every time bore restarts. Anyone who finds the port can try to connect, so always use a password and `--ssl` when the chat is exposed to the internet.

**Alternative:** [Tailscale](https://tailscale.com/) creates a private network between you and your friends — no tunnel, no public exposure, and the address doesn't change. Everyone needs the Tailscale app installed.

## Commands

| Command | Who | Description |
|---|---|---|
| `/who` | everyone | List who's online |
| `/msg <name> <text>` | everyone | Private message, only the recipient sees it |
| `/kick <name>` | host | Remove a participant from the chat |
| `/help` | everyone | Show available commands |
| `exit` | everyone | Leave the chat (host: close the chat for everyone) |

## Joining from Windows

Windows doesn't ship `nc` or `openssl`. Options:

- **ncat** — installed together with [Nmap](https://nmap.org/download):
  `ncat bore.pub 12736` or, for `--ssl` mode, `ncat --ssl bore.pub 12736`
- **WSL** — regular Linux `nc` / `openssl`
- **Git Bash** — includes `openssl`

Use Windows Terminal for proper colors.

## How it works

```
               ┌────────────── server (host) ──────────────┐
 participant ──┤ handle_client thread ──┐                  │
 participant ──┤ handle_client thread ──┼─► broadcast() ──►│── everyone else
 participant ──┤ handle_client thread ──┘                  │
               │ accept_loop thread  (accepts new clients) │
               │ main thread         (host's keyboard)     │
               └───────────────────────────────────────────┘
```

- **`accept_loop`** runs in the background and accepts new connections; each one gets its own **`handle_client`** thread.
- **`handle_client`** checks the password, asks for a name, then reads that participant's messages and **broadcasts** them to everyone else.
- **The main thread** reads the host's keyboard input, so the host can chat and run `/kick`.
- **Locks** protect the shared `clients` dict and keep two threads from writing to sockets at the same time.
- **The input-line trick:** `nc` and `openssl` have no UI of their own, so the server draws one remotely with ANSI escape codes — it inserts each incoming message as a new line above the participant's input line and puts the cursor back where it was.

## Limitations

- Messages longer than the terminal width can wrap over the input line.
- Participants' own messages appear without a timestamp — that's their local echo, which the server doesn't control.
- With `nc`, the password is visible on screen while typing.
- The certificate is self-signed, so it encrypts traffic but doesn't prove the server's identity.
- The default port is `33000`.
