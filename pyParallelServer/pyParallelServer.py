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
        self.servsock = TCP_ServSockWrapper(IP,port,nConnections) 
        #our process pool
        self.nProcesses = nProcesses
        self.procPool = mp.Pool(processes=self.nProcesses)
        self.runProcessPool()
        self.procPool.close()
        self.procPool.join()
     
    def runProcessPool(self):
        res = self.procPool.map_async(runChildProcess,[self.servsock for proc in range(self.nProcesses)])
       
    
def runChildProcess(servsock):
    print('started')
    print(servsock)
    childServ = ChildServer(servsock)
    childServ.workWithClients()

class ChildServer(Connection):

    def __init__(self,servsock,sendBufLen=2048, timeOut=30):
        super().__init__(sendBufLen, timeOut)
        self.talksock = None
        self.servsock = servsock
        #get id from client
        self.fillCommandDict()
       
    def fillCommandDict(self):
        self.commands.update({'echo':self.echo,
                              'time':self.time,
                              'quit':self.quit,
                              'download':self.sendFileTCP,
                              'upload':self.recvFileTCP})

    def registerNewClient(self):
       sock, addr = self.servsock.raw_sock.accept()
       self.talksock = SockWrapper(raw_sock=sock,inetAddr=addr)
       

    def workWithClients(self):
        while True:
            self.registerNewClient()
            self.clientCommandsHandling()

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
        self.servsock.raw_sock.settimeout(timeOut)
        try:
            self.talksock = self.registerNewClient()
        except OSError as e:
            #disable timeout
            self.servsock.raw_sock.settimeout(None)
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
   
    