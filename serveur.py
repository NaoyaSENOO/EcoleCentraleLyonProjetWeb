#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jun 10 08:48:14 2024

@author: Naoyasenoo
"""
import http.server
import socketserver
from urllib.parse import urlparse, parse_qs, unquote
import json
import datetime as dt
import sqlite3
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Numéro de port TCP
port_serveur = 8080

# Configuration de la connexion à la base de données
conn = sqlite3.connect('donnees.db')

class RequestHandler(http.server.SimpleHTTPRequestHandler):
    static_dir = 'client'  # Répertoire contenant les fichiers statiques pour le client

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=self.static_dir, **kwargs)
        

    def do_GET(self):
        self.init_params()
        
        if self.path_info[0] == 'station':
            self.send_station()
        elif self.path_info[0] == 'debit':
            self.send_debit_data()
        else:
            super().do_GET()
    
    def update_dates(self):
        # Récupérer les nouvelles dates depuis les paramètres de la requête
        self.start_date = self.params.get('start_date', [''])[0]
        self.end_date = self.params.get('end_date', [''])[0]
     
    def update_types(self):
        data_types = self.params.get('dataType', ['tous'])  #s'il y a pas de info par le client on prend 'tous'
        return data_types

    def send_station(self):
        """Générer une réponse avec la liste des points d'intérêt"""
        c = conn.cursor()
        c.execute("SELECT CdStationHydro, LbStationHydro, X, Y FROM StationsHydro WHERE DtFermetureStationHydro IS NULL")
        r = c.fetchall()
        body = json.dumps([{'code': cd, 'nom': n, 'longitude': lon, 'latitude': lat} 
                        for (cd, n, lat, lon) in r])
        headers = [('Content-Type', 'application/json')]
        

        self.send(body, headers)

    def send_debit_data(self):
        c = conn.cursor()
        print(self.path_info)
        # s'il n'y a pas de paramètre => erreur pas de station
        if len(self.path_info) <= 1 or self.path_info[1] == '' :
            print ('Erreur pas de nom')
            self.send_error(404)    # station non spécifiée -> erreur 404
            print('station non spécifiée')
            return None
        else:
            # on récupère le nom de la station dans le 1er paramètre
            station = self.path_info[1]
            # On teste que la station demandée existe bien
            c.execute("SELECT LbStationHydro FROM StationsHydro")
            r = c.fetchall()

        # Remarque : r est une liste de tuples à 1 seul élément
        if (station,) not in r:
            # station non trouvée -> erreur 404
            print ('Erreur nom')
            self.send_error(404)
            return None
        
        
        #on prendre 8 premier chiffre 
        c.execute("SELECT CdStationHydro FROM StationsHydro WHERE LbStationHydro = ?", (station,))
        result = c.fetchone()
        infos = [result[0][:8]]

        start_date = self.path_info[2].replace('-','/')
        end_date = self.path_info[3].replace('-','/')
        print(start_date)

        infos.append(start_date)
        infos.append(end_date)

        
        #---------------------------------------------------------------------------------------------------
        data_types = self.path_info[4] #s'il y a pas de info par le client on prend 'tous'
        print(data_types)
        if data_types :
            infos.append(data_types)
        print(infos)
        # verifier le cache si il y a deja des figures
        ###il faut changer le code de SQLite (en bas)pour que il correspondre a notre fiche
        #---------------------------------------------------------------------------------------------------
        c.execute("SELECT FilePath FROM GraphCache WHERE StationCode = ? AND StartDate = ? AND EndDate = ? AND  DataTypes= ?", tuple(infos))
        cache_hit = c.fetchone()
        if cache_hit:
            print(cache_hit)
            body = json.dumps({"img": f"/{cache_hit[0]}"})
            self.send(body, [('Content-Type', 'application/json')])
            print('déjà vu')
            return
        
        else:
            query2 = 'SELECT Date, "Moyenneinterannuelle(m3/s)", "Valeurforte(m3/s)", "Valeurfaible(m3/s)" FROM Hydrometrie WHERE CodesiteHydro3= ? AND ("Moyenneinterannuelle(m3/s)" IS NOT NULL OR "Valeurforte(m3/s)" IS NOT NULL OR "Valeurfaible(m3/s)" IS NOT NULL) ORDER BY Date'
            c.execute(query2, (infos[0],))
        
            records = c.fetchall()
            print(len(records))
            if not records:
                body = json.dumps({'img' : f"/pas_de_donnees_dispo.png"\
                                })
                headers = [('Content-Type', 'application/json')]
                self.send(body, headers)                
                return

            sdate=dt.datetime.strptime(start_date, "%d/%m/%Y")
            edate=dt.datetime.strptime(end_date, "%d/%m/%Y")
            dates=[]
            averages=[]
            maximums=[]
            minimums=[]
            for record in records:
                date=dt.datetime.strptime(record[0], "%d/%m/%Y")
                if date>=sdate and date<=edate :
                    dates.append(date)
                    averages.append(record[1])
                    maximums.append(record[2])
                    minimums.append(record[3])
            
            # Création du graphique
            #---------------------------------------------------------------------------------------------------
            plt.figure(figsize=(10, 5))
            if 'moy'==data_types or 'tous'==data_types:
                plt.scatter(dates, averages, label="Débit moyen (m3/s)", color='blue')
            if 'min'==data_types or 'tous'==data_types:
                plt.scatter(dates, maximums, label="Débit maximum (m3/s)", color='green')
            if 'max'==data_types or 'tous'==data_types:
                plt.scatter(dates, minimums, label="Débit minimum (m3/s)", color='red')
        
            plt.xlabel('Date')
            plt.ylabel('Débit (m3/s)')
            plt.title(f'Données de débit pour la station {station}')
            plt.legend()
            plt.grid(True)
        
            
            # Sauvegarde du graphique en tant que fichier image 
            ###il faut modifier le nom de image_path
            date_d=infos[1].replace("/","-")
            date_f=infos[2].replace("/","-")
            image_path = f'debit_de_{infos[0]}_from_{date_d}_to_{date_f}_{infos[3]}.png'
            infos.append(image_path)
            plt.savefig(f'client/{image_path}')
            plt.close()
            
            # ajouter le figure(image_path)dans le fiche
            #---------------------------------------------------------------------------------------------------
            c.execute("INSERT INTO GraphCache (StationCode, StartDate, EndDate, DataTypes, FilePath) VALUES (?, ?, ?, ?, ?)", tuple(infos))
            conn.commit()

            # Envoi de l'URL de l'image au client en format JSON
            body = json.dumps({'img' : f"/{image_path}"\
                               })
            headers = [('Content-Type', 'application/json')]
            self.send(body, headers)
            return

    def send(self, body, headers=[]):
        """Envoyer la réponse au client avec le corps et les en-têtes fournis"""
        encoded = bytes(body, 'UTF-8')
        self.send_response(200)
        [self.send_header(*t) for t in headers]
        self.send_header('Content-Length', int(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def init_params(self):
        """Analyser la requête pour initialiser nos paramètres"""
        info = urlparse(self.path)
        self.path_info = [unquote(v) for v in info.path.split('/')[1:]]
        self.query_string = info.query
        self.params = parse_qs(info.query)
        length = self.headers.get('Content-Length')
        ctype = self.headers.get('Content-Type')
        if length:
            self.body = str(self.rfile.read(int(length)), 'utf-8')
            if ctype == 'application/x-www-form-urlencoded':
                self.params = parse_qs(self.body)
            elif ctype == 'application/json':
                self.params = json.loads(self.body)
        else:
            self.body = ''
        print('init_params|info_path =', self.path_info)
        print('init_params|body =', length, ctype, self.body)
        print('init_params|params =', self.params)

# Démarrage du serveur
httpd = socketserver.TCPServer(("", port_serveur), RequestHandler)
print("Serveur lancé sur le port :", port_serveur)
httpd.serve_forever()
