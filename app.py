# app.py

import base64
import hmac
import hashlib 
import requests
import tomllib

from flask import Flask, render_template, request, url_for, redirect
from urllib.parse import quote_plus, parse_qs
from time import strftime, gmtime

app = Flask(__name__)
app.config.from_file("config.toml", load=tomllib.load, text=False)
app.config.update(
  SSO_SECRET = str.encode(app.config['SSO_SECRET']),
  # Our auth headers, from above.
  HEADERS = {'Api-Key': app.config['DISCOURSE_API_KEY'],
             'Api-Username': app.config['DISCOURSE_API_USER'],
             'User-Agent': app.config['USER_AGENT']}
)

# Routes

@app.route("/", methods=['GET', 'POST'])
def index():
  if request.method == 'POST':
    url = build_discourse_sso()
    return redirect(url)
    
  return render_template("index.html")

@app.route("/r")
def return_path():
  result = parse_return(request.args)
  return render_template("return.html")

# Functions

def build_discourse_sso():
  # Reference material for Discourse SSO
  # https://meta.discourse.org/t/use-discourse-as-an-identity-provider-sso-discourseconnect/32974

  # Not the best cryptographic nonce but it'll do here
  nonce = strftime("%s",gmtime())

  payload = "nonce=" + nonce + \
            "&return_sso_url=" + \
            app.config['RETURN_URL'] + url_for('return_path')

  base64_payload = base64.b64encode(bytes(payload, 'utf-8'))
  url_encoded_payload = quote_plus(base64_payload)
  hex_signature = hmac.new(app.config['SSO_SECRET'],
                        url_encoded_payload.encode("utf-8"),
                        hashlib.sha256).hexdigest()

  url = app.config['DISCOURSE'] + \
        "/session/sso_provider" + \
        "?sso=" + url_encoded_payload + \
        "&sig=" + hex_signature
  return(url)

def parse_return(args):
  sso = args['sso']
  sig = args['sig']

  sso_signature = hmac.new(app.config['SSO_SECRET'],
                  sso.encode("utf-8"), hashlib.sha256).hexdigest()
  
  user = parse_qs(base64.b64decode(sso).decode("utf-8"))['username'][0]
  award_discourse_badge(app.config['BADGE_ID'], user)

# Thanks to Fedora for this code snippet
# https://pagure.io/badgebot/blob/main/f/badgemirror.py#_167
def award_discourse_badge(badge_id, user):
    print(f"Awarding `{badge_id}` to `{user}`")
    # You can also add a "reason", which must link to a post or topic.
    bestow = {'username': f"{user}", 'badge_id': f'{badge_id}'}
    r = requests.post(f"{app.config['DISCOURSE']}/user_badges",
                      json=bestow, headers=app.config['HEADERS'])
    if r.status_code != 200:
        print(f"Error granting badge: got {r.status_code}")
 
    print(f'{user} has been awarded the {badge_id} badge!')
