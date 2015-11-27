import sys  #for IP and port passing
import socket
import re   #regular expressions
from Connection import Connection
from FileWorker import*
from SocketWrapper import*
import time
import multiprocessing as mp

#def servWork(serv):
#    serv.

class TCPServer(Connection):

    def __init__(self, IP,port,nConnections = 1,sendBuflen = 2048,timeOut = 15):
        super().__init__(sendBuflen,timeOut)
        self.servSock = TCP_ServSockWrapper(IP,port,nConnections) 
        self.talksock = None ##
        self.fillCommandDict()
        self.clientsId = [] ##
        self.childProcesses = []


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


    def clientCommandsHandling(self):
        while True:
            try:
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


    def writeClientId(self,id):
        if len(self.clientsId) == 2:
            #pop old id
            self.clientsId.pop(0)
        #write new id
        self.clientsId.append(id)
            
                    
    def registerNewClient(self):
        sock, addr = self.servSock.raw_sock.accept()
        self.talksock = SockWrapper(raw_sock=sock,inetAddr=addr)
        #get id from client
        id = self.talksock.recvInt()
        self.writeClientId(id)
        return self.talksock

    def workWithClients(self):
        while True:
            self.registerNewClient()
            #self.clientCommandsHandling()
            self.updateChildProcesses()
    
    def updateChildProcesses(self):
        childProc = mp.Process(target=self.clientCommandsHandling,args=())
        childProc.start()
        self.childProcesses = [proc for proc in self.childProcesses if proc.is_alive() == True]
        self.childProcesses.append(childProc)


if __name__ == "__main__":
    
    server = TCPServer("192.168.1.2","6000")
    server.workWithClients()
   
    