#!/usr/bin/env python3
"""
Abre automaticamente o navegador padrão na página do servidor local (localhost:8000) e inicia um servidor HTTP simples na porta 8000.
"""
import http.server
import os

os.system('firefox http://localhost:8000')
http.server.test(HandlerClass=http.server.SimpleHTTPRequestHandler, port=8000)
