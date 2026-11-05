# test_v016_redact_tokens.py - v0.16 (11-02-2026): access tokens never reach
# the session log. 'm365 ... --debug' (the Troubleshooting advice for
# 'Error: [object Object]') prints each request's headers, including
# 'authorization: Bearer <token>' (CLI request.js, found 11-02-2026). The
# log file and the Run-for-each-CSV-row record go through redact_secrets,
# which masked only passwords before.
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import m365_catalog as cat

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

JWT = ("eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9."
       "eyJhdWQiOiJodHRwczovL2dyYXBoLm1pY3Jvc29mdC5jb20ifQ."
       "c2lnbmF0dXJlLXBhcnQtZm9yLXRlc3Rpbmc")
debug = ('Request:\n{\n  "url": "https://graph.microsoft.com/v1.0/me",\n  "headers": {\n'
         '    "authorization": "Bearer %s",\n    "accept": "application/json"\n  }\n}\n' % JWT)
out = cat.redact_secrets(debug)
check(JWT not in out and "eyJ" not in out, "a --debug request block keeps no token")
check('"authorization": "Bearer ********"' in out, "the header shows that a token was there")
check('"url": "https://graph.microsoft.com/v1.0/me"' in out and '"accept": "application/json"' in out,
      "the rest of the debug text is unchanged")
check(cat.redact_secrets("token " + JWT + " end") == "token ******** end",
      "a bare token is masked too")
check(cat.redact_secrets("Authorization: bearer abcdefghijklmnopqrstuvwxyz0123") ==
      "Authorization: bearer ********", "any case of 'Bearer' is masked")
check(cat.redact_secrets("entra user set --userName a@example.com --password Secret123!x") ==
      "entra user set --userName a@example.com --password ********", "passwords are still masked")
plain = "Bearer Creek Elementary - 12 devices; eyJ is not a token on its own"
check(cat.redact_secrets(plain) == plain, "ordinary text (short words after 'Bearer') is left alone")
check(cat.redact_secrets(None) == "None" and cat.redact_secrets(42) == "42",
      "anything that is not text still works")
print("FAILURES:", len(fails))
sys.exit(1 if fails else 0)
