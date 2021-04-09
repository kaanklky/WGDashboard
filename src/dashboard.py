import ifcfg
import os
from flask import Flask, request, render_template, redirect, url_for
import subprocess
from datetime import datetime, date, time, timedelta
from operator import itemgetter
from tinydb import TinyDB, Query

conf_location = "/etc/wireguard"
app = Flask("Wireguard Dashboard")
app.config['TEMPLATES_AUTO_RELOAD'] = True
conf_data = {}


def get_conf_peer_key(config_name):
    keys = []
    try:
        peer_key = subprocess.check_output("wg show " + config_name + " peers", shell=True)
    except Exception:
        return "stopped"
    peer_key = peer_key.decode("UTF-8").split()
    for i in peer_key: keys.append(i)
    return keys


def get_conf_running_peer_number(config_name):
    running = 0
    # Get latest handshakes
    try:
        data_usage = subprocess.check_output("wg show " + config_name + " latest-handshakes", shell=True)
    except Exception:
        return "stopped"
    data_usage = data_usage.decode("UTF-8").split()
    count = 0
    now = datetime.now()
    b = timedelta(minutes=2)
    for i in range(int(len(data_usage) / 2)):
        minus = now - datetime.fromtimestamp(int(data_usage[count + 1]))
        if minus < b:
            running += 1
        count += 2
    return running

def read_conf_file(config_name):
    # Read Configuration File Start
    conf_location = "/etc/wireguard/" + config_name + ".conf"
    f = open(conf_location, 'r')
    file = f.read().split("\n")
    conf_peer_data = {
        "Interface": {},
        "Peers": []
    }
    peers_start = 0
    for i in range(len(file)):
        if file[i] == "[Peer]":
            peers_start = i
            break
        else:
            if len(file[i]) > 0:
                if file[i] != "[Interface]":
                    tmp = file[i].replace(" ", "").split("=", 1)
                    if len(tmp) == 2:
                        conf_peer_data['Interface'][tmp[0]] = tmp[1]
    conf_peers = file[peers_start:]
    peer = -1
    for i in conf_peers:
        if i == "[Peer]":
            peer += 1
            conf_peer_data["Peers"].append({})
        else:
            if len(i) > 0:
                tmp = i.replace(" ", "").split("=", 1)
                if len(tmp) == 2:
                    conf_peer_data["Peers"][peer][tmp[0]] = tmp[1]
    # Read Configuration File End
    return conf_peer_data



def get_conf_peers_data(config_name):
    db = TinyDB('db/' + config_name + '.json')
    peers = Query()
    conf_peer_data = read_conf_file(config_name)

    for i in conf_peer_data['Peers']:
        if not db.search(peers.id == i['PublicKey']):
            db.insert({
                "id": i['PublicKey'],
                "name": "",
                "total_receive": 0,
                "total_sent": 0,
                "total_data": 0,
                "endpoint": 0,
                "status": 0,
                "latest_handshake": 0,
                "allowed_ip": 0,
                "traffic": []
            })

        # Get latest handshakes
        try:
            data_usage = subprocess.check_output("wg show " + config_name + " latest-handshakes", shell=True)
        except Exception:
            return "stopped"
        data_usage = data_usage.decode("UTF-8").split()
        count = 0
        now = datetime.now()
        b = timedelta(minutes=2)
        for i in range(int(len(data_usage) / 2)):
            minus = now - datetime.fromtimestamp(int(data_usage[count + 1]))
            if minus < b:
                status = "running"
            else:
                status = "stopped"
            if int(data_usage[count + 1]) > 0:
                db.update({"latest_handshake": str(minus).split(".")[0], "status": status},
                          peers.id == data_usage[count])
            else:
                db.update({"latest_handshake": "(None)", "status": status}, peers.id == data_usage[count])
            count += 2

    # Get transfer
    try:
        data_usage = subprocess.check_output("wg show " + config_name + " transfer", shell=True)
    except Exception:
        return "stopped"
    data_usage = data_usage.decode("UTF-8").split()
    count = 0
    for i in range(int(len(data_usage) / 3)):
        cur_i = db.search(peers.id == data_usage[count])
        total_sent = cur_i[0]['total_sent']
        total_receive = cur_i[0]['total_receive']
        cur_total_sent = round(int(data_usage[count + 2]) / (1024 ** 3), 4)
        cur_total_receive = round(int(data_usage[count + 1]) / (1024 ** 3), 4)
        if cur_i[0]["status"] == "running":
            if total_sent <= cur_total_sent:
                total_sent = cur_total_sent
            else: total_sent += cur_total_sent

            if total_receive <= cur_total_receive:
                total_receive = cur_total_receive
            else: total_receive += cur_total_receive
            db.update({"total_receive": round(total_receive,4),
                       "total_sent": round(total_sent,4),
                       "total_data": round(total_receive + total_sent, 4)}, peers.id == data_usage[count])

        # Will get implement in the future
        # traffic = db.search(peers.id == data_usage[count])[0]['traffic']
        # traffic.append({"time": current_time, "total_receive": round(int(data_usage[count + 1]) / (1024 ** 3), 4),
        #                 "total_sent": round(int(data_usage[count + 2]) / (1024 ** 3), 4)})
        # db.update({"traffic": traffic}, peers.id == data_usage[count])

        count += 3

    # Get endpoint
    try:
        data_usage = subprocess.check_output("wg show " + config_name + " endpoints", shell=True)
    except Exception:
        return "stopped"
    data_usage = data_usage.decode("UTF-8").split()
    count = 0
    for i in range(int(len(data_usage) / 2)):
        db.update({"endpoint": data_usage[count + 1]}, peers.id == data_usage[count])
        count += 2

    # Get allowed ip
    for i in conf_peer_data["Peers"]:
        db.update({"allowed_ip":i['AllowedIPs']}, peers.id == i["PublicKey"])


def get_peers(config_name):
    get_conf_peers_data(config_name)
    db = TinyDB('db/' + config_name + '.json')
    result = db.all()
    result = sorted(result, key=lambda d: d['status'])
    return result


def get_conf_pub_key(config_name):
    try:
        pub_key = subprocess.check_output("wg show " + config_name + " public-key", shell=True, stderr=subprocess.STDOUT)
    except Exception:
        return "stopped"
    return pub_key.decode("UTF-8")


def get_conf_listen_port(config_name):
    try:
        pub_key = subprocess.check_output("wg show " + config_name + " listen-port", shell=True,
                                          stderr=subprocess.STDOUT)
    except Exception:
        return "stopped"
    return pub_key.decode("UTF-8")


def get_conf_total_data(config_name):
    db = TinyDB('db/' + config_name + '.json')
    upload_total = 0
    download_total = 0
    for i in db.all():
        upload_total += round(i['total_sent'],4)
        download_total += round(i['total_receive'],4)
    total = round(upload_total + download_total, 4)
    return [total, upload_total, download_total]


def get_conf_status(config_name):
    ifconfig = dict(ifcfg.interfaces().items())
    if config_name in ifconfig.keys():
        return "running"
    else:
        return "stopped"


def get_conf_list():
    conf = []
    for i in os.listdir(conf_location):
        if not i.startswith('.'):
            if ".conf" in i:
                i = i.replace('.conf', '')
                temp = {"conf": i, "status": get_conf_status(i), "public_key": get_conf_pub_key(i)}
                if temp['status'] == "running":
                    temp['checked'] = 'checked'
                else:
                    temp['checked'] = ""
                conf.append(temp)
    conf = sorted(conf, key=itemgetter('status'))
    return conf


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', conf=get_conf_list())


@app.route('/configuration/<config_name>', methods=['GET'])
def conf(config_name):
    conf_data = {
        "name": config_name,
        "status": get_conf_status(config_name),
        "checked": ""
    }
    if conf_data['status'] == "stopped":
        return redirect('/')
    else:
        conf_data['checked'] = "checked"
        return render_template('configuration.html', conf=get_conf_list(), conf_data=conf_data)


@app.route('/get_config/<config_name>', methods=['GET'])
def get_conf(config_name):
    db = TinyDB('db/' + config_name + '.json')

    conf_data = {
        "peer_data": get_peers(config_name),
        "name": config_name,
        "status": get_conf_status(config_name),
        "total_data_usage": get_conf_total_data(config_name),
        "public_key": get_conf_pub_key(config_name),
        "listen_port": get_conf_listen_port(config_name),
        "running_peer": get_conf_running_peer_number(config_name),
    }
    if conf_data['status'] == "stopped":
        return redirect('/')
    else:
        conf_data['checked'] = "checked"
        return render_template('get_conf.html', conf=get_conf_list(), conf_data=conf_data)


@app.route('/switch/<config_name>', methods=['GET'])
def switch(config_name):
    status = get_conf_status(config_name)
    if status == "running":
        try:
            status = subprocess.check_output("wg-quick down " + config_name, shell=True)
        except Exception:
            return redirect('/')
    elif status == "stopped":
        try:
            status = subprocess.check_output("wg-quick up " + config_name, shell=True)
        except Exception:
            return redirect('/')
    return redirect('/')


@app.route('/add_peer/<config_name>', methods=['POST'])
def add_peer(config_name):
    data = request.get_json()
    public_key = data['public_key']
    allowed_ips = data['allowed_ips']
    keys = get_conf_peer_key(config_name)
    if public_key in keys:
        return "Key already exist."
    else:
        status = ""
        try:
            status = subprocess.check_output(
                "wg set " + config_name + " peer " + public_key + " allowed-ips " + allowed_ips, shell=True,
                stderr=subprocess.STDOUT)
            status = subprocess.check_output("wg-quick save " + config_name, shell=True, stderr=subprocess.STDOUT)
            return "true"
        except subprocess.CalledProcessError as exc:
            return exc.output.strip()

            # return redirect('/configuration/'+config_name)


@app.route('/remove_peer/<config_name>', methods=['POST'])
def remove_peer(config_name):
    db = TinyDB("db/" + config_name + ".json")
    peers = Query()
    data = request.get_json()
    delete_key = data['peer_id']
    keys = get_conf_peer_key(config_name)
    if delete_key not in keys:
        return "This key does not exist"
    else:
        try:
            status = subprocess.check_output("wg set " + config_name + " peer " + delete_key + " remove", shell=True,
                                             stderr=subprocess.STDOUT)
            status = subprocess.check_output("wg-quick save " + config_name, shell=True, stderr=subprocess.STDOUT)
            db.remove(peers.id == delete_key)
            return "true"
        except subprocess.CalledProcessError as exc:
            return exc.output.strip()


@app.route('/save_peer_name/<config_name>', methods=['POST'])
def save_peer_name(config_name):
    data = request.get_json()
    id = data['id']
    name = data['name']
    db = TinyDB("db/" + config_name + ".json")
    peers = Query()

    db.update({"name": name}, peers.id == id)
    return id + " " + name


@app.route('/get_peer_name/<config_name>', methods=['POST'])
def get_peer_name(config_name):
    data = request.get_json()
    id = data['id']
    db = TinyDB("db/" + config_name + ".json")
    peers = Query()
    result = db.search(peers.id == id)
    return result[0]['name']

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=False, port=10086)