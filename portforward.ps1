netsh interface portproxy delete v4tov4 listenaddress=172.16.2.105 listenport=7770
netsh interface portproxy add v4tov4 listenaddress=172.16.2.105 listenport=7770 connectaddress=127.0.0.1 connectport=7770
