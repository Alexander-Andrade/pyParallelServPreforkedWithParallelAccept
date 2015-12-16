import sys  #for IP and port passing
import socket
import re   #regular expressions
from Connection import Connection
from FileWorker import*
from SocketWrapper import*
import time
import multiprocessing as mp
#from multiprocessing.reduction import re

# make sockets pickable/inheritable
if sys.platform == 'win32':
    import multiprocessing.reduction

class ParentServer:

    def __init__(self, IP,port,nConnections = 3,nProcesses = 3):
        self.servSock = TCP_ServSockWrapper(IP,port,nConnections) 
        #clients number
        self.nClients = 0
        #our process pool
        self.nProcesses = nProcesses
        self.procPool = mp.Pool(processes=self.nProcesses)
  

    def onClientGone(self,res):
        #callback func, is called, when
        #one client stop working with server 
        self.nClients -= 1;

         
    def registerNewClient(self):
        sock, addr = self.servSock.raw_sock.accept()
        talksock = SockWrapper(raw_sock=sock,inetAddr=addr)
        return talksock

    def workWithClients(self):
        while True:
            sock = self.registerNewClient()
            self.updateProcessPool(sock)
    
    def updateProcessPool(self,sock):
        if self.nClients < self.nProcesses:
            self.nClients += 1;
            res = self.procPool.apply_async(runChildProcess,args=(sock,),callback=self.onClientGone)
       
    

def runChildProcess(talksock):
    print('started')
    print(talksock)
    childServ = ChildServer(talksock)
    childServ.clientCommandsHandling()

class ChildServer(Connection):

    def __init__(self,sock,sendBufLen=2048, timeOut=30):
        super().__init__(sendBufLen, timeOut)
        self.talksock = sock
        #get id from client
        self.fillCommandDict()
       


    def fillCommandDict(self):
        self.commands.update({'echo':self.echo,
                              'time':self.time,
                              'quit':self.quit,
                              'download':self.sendFileTCP,
                              'upload':self.recvFileTCP})

    def echo(self,commandArgs):
        self.talksock.sendMsg(commandArgs)


    def time(self,commandArgs):
        self.talksock.sendMsg(time.asctime())

    def quit(self,commandArgs):
        self.talksock.shutdown(socket.SHUT_RDWR)
        self.talksock.close()


    def sendFileTCP(self,commandArgs):
        self.sendfile(self.talksock,commandArgs,self.recoverTCP)
        self.talksock.sendMsg("file downloaded")


    def recvFileTCP(self,commandArgs):
        self.receivefile(self.talksock,commandArgs,self.recoverTCP)
        self.talksock.sendMsg("file uploaded")


    def recoverTCP(self,timeOut):
        self.servSock.raw_sock.settimeout(timeOut)
        try:
            self.talksock = self.registerNewClient()
        except OSError as e:
            #disable timeout
            self.servSock.raw_sock.settimeout(None)
            raise 
        #compare prev and cur clients id's, may be the same client
        if self.clientsId[0] != self.clientsId[1]:
            raise OSError("new client has connected")
        return self.talksock


    def writeClientId(self,id):
        if len(self.clientsId) == 2:
            #pop old id
            self.clientsId.pop(0)
        #write new id
        self.clientsId.append(id)


    def clientCommandsHandling(self):
        while True:
            try:
                print('inside')
                message = self.talksock.recvMsg()
                
                if len(message) == 0:
                    break
                
                regExp = re.compile("[A-Za-z0-9_]+ *.*")
                if regExp.match(message) is None:
                    self.talksock.sendMsg("invalid command format \"" + message + "\"")
                    continue
                
                
                if not self.catchCommand(message):
                    self.talksock.sendMsg("unknown command")
                
                #quit
                if message.find("quit") != -1:
                    break
                
            except FileWorkerError as e:
                #can work with the same client
                print(e)
                
            except (OSError,FileWorkerCritError):
                break



if __name__ == "__main__":
    
    server = ParentServer("192.168.1.2","6000")
    server.workWithClients()
   
    