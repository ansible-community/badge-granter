# app.py

import tomllib
import base64
import hmac
import hashlib 
import requests
import io

from flask import Flask, render_template, request, url_for, redirect
from urllib import parse
from urllib.parse import quote_plus, parse_qs
from time import strftime, gmtime
from qrcode import make as qrmake

app = Flask(__name__)
app.config.from_file("config.toml", load=tomllib.load, text=False)
app.config.update(
  SSO_SECRET = str.encode(app.config['SSO_SECRET']),
  # Our auth headers, from above.
  HEADERS = {'Api-Key': app.config['DISCOURSE_API_KEY'],
             'Api-Username': app.config['DISCOURSE_API_USER'],
             'User-Agent': app.config['USER_AGENT']}
)
with open("config.toml", "rb") as f:
  badge_config = tomllib.load(f)['badges']

# This block is only needed if running behind a reverse proxy (i.e. when in production)
# Comment it out for dev work
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(
  app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)

# Routes

@app.route("/")
def index():
    return render_template("base.html")

@app.route("/b/<uuid>", methods=['GET', 'POST'])
def badge(uuid):
    if uuid in badge_config.keys():
        name     = badge_config[uuid]['name']
        img_cdn  = badge_config[uuid]['img_cdn']

        if request.method == 'POST':
            url = build_discourse_sso(uuid)
            return redirect(url)

        return render_template("badge.html", uuid=uuid, name=name, img_cdn=img_cdn)

    return render_template('not_found.html'), 404

@app.route("/r/<uuid>")
def return_path(uuid):
    if uuid in badge_config.keys():
        badge_id = badge_config[uuid]['badge_id']
        img_cdn  = badge_config[uuid]['img_cdn']
        redir    = app.config['DISCOURSE'] + badge_config[uuid]['redirect']

        result = parse_return(request.args, badge_id)
        if result:
            # redirect to the Discourse page
            return redirect(redir)
        else:
            return render_template("failed.html")

    return render_template('not_found.html'), 404

@app.route("/qr/<uuid>")
def qrcode(uuid):
    if uuid in badge_config.keys():
        name     = badge_config[uuid]['name']
        img_cdn  = badge_config[uuid]['img_cdn']

        # make QR
        img = qrmake(app.config['RETURN_URL'] + url_for('badge', uuid=uuid))
        obj = io.BytesIO()             # file in memory to save image without using disk  #
        img.save(obj)                  # save in file (BytesIO)
        obj.seek(0)                    # move to beginning of file (BytesIO) to read it   #

        # convert to bases64
        data = obj.read()              # get data from file (BytesIO)
        data = base64.b64encode(data)  # convert to base64 as bytes
        data = data.decode()           # convert bytes to string

        # convert to <img> with embed image
        qr = 'data:image/png;base64,{}'.format(data)

        return render_template('qr.html',qr=qr, img_cdn=img_cdn, name=name)

    return render_template('not_found.html'), 404

# Functions

def build_discourse_sso(uuid):
  # Reference material for Discourse SSO
  # https://meta.discourse.org/t/use-discourse-as-an-identity-provider-sso-discourseconnect/32974

  # Not the best cryptographic nonce but it'll do here
  nonce = strftime("%s",gmtime())

  payload = str.encode("nonce=" + nonce + "&return_sso_url=" + \
            app.config['RETURN_URL'] + url_for('return_path', uuid=uuid))

  BASE64_PAYLOAD = base64.b64encode(payload)
  URL_ENCODED_PAYLOAD = parse.quote(BASE64_PAYLOAD)

  sig = hmac.new(app.config['SSO_SECRET'], BASE64_PAYLOAD, hashlib.sha256)
  HEX_SIGNATURE = sig.hexdigest()

  url = app.config['DISCOURSE'] + \
        "/session/sso_provider?sso=" + URL_ENCODED_PAYLOAD + \
        "&sig="+HEX_SIGNATURE
  return(url)

def parse_return(args, badge_id):
  sso = args['sso']
  sig = args['sig']

  sso_signature = hmac.new(app.config['SSO_SECRET'],
                  sso.encode("utf-8"), hashlib.sha256).hexdigest()
  
  user = parse_qs(base64.b64decode(sso).decode("utf-8"))['username'][0]
  return award_discourse_badge(badge_id, user)

# Thanks to Fedora for this code snippet
# https://pagure.io/badgebot/blob/main/f/badgemirror.py#_167
def award_discourse_badge(badge_id, user):
    # You can also add a "reason", which must link to a post or topic.
    bestow = {'username': f"{user}", 'badge_id': f'{badge_id}'}
    r = requests.post(f"{app.config['DISCOURSE']}/user_badges",
                      json=bestow, headers=app.config['HEADERS'])
    if r.status_code == 200:
        print(f'{user} has been awarded the {badge_id} badge!')
        return(True)
    
    print(f"Error granting badge: got {r.status_code}")
    return(False)
