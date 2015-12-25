import sys  #for IP and port passing
import socket
import re   #regular expressions
from Connection import Connection
from FileWorker import*
from SocketWrapper import*
import time
import multiprocessing as mp
from ctypes import Structure,c_int
#from multiprocessing.reduction import re

# make sockets pickable/inheritable
if sys.platform == 'win32':
    import multiprocessing.reduction

class ProcStatistics(Structure):
    _fields_ = [('nproc',c_int),('nclients',c_int)]


def showSharedStatusInfo(procStat):
    print('processes : ' + str(procStat.nproc),end='  ')
    print('cients : ' + str(procStat.nclients),end='  ',flush=True)

class ParentServer:

    def __init__(self, IP,port,nConnections = 5,nmin=3,nmax=5,timeout = 30):
        self.servsock = TCP_ServSockWrapper(IP,port,nConnections) 
        #min and max number of processes in the pool
        self.nmin = nmin
        self.nmax = nmax
        #tools for process sync
        self.procManager = mp.Manager()
        #event
        self.onClientComeEvent = self.procManager.Event()
        #shared memmory for counting busy processess
        self.procStat = mp.Value(ProcStatistics,0,lock=True) 
        #timeout for accept
        self.timeout = timeout
        self.runProcessPool()
        self.monitorProcessPool()

        
    def runProcessPool(self):
        #base processess
        isBaseProcess = True
        for i in range(self.nmin):
            mp.Process(target=runChildProcess,args=(self.servsock,self.procStat,self.onClientComeEvent,isBaseProcess,self.timeout)).start()
    
    def monitorProcessPool(self):
        isBaseProcess = False
        while True:
            #waiting event of new client come
            self.onClientComeEvent.wait()
            self.onClientComeEvent.clear()
            #number of processes equ number of clients(no available processess)
            if self.procStat.nproc == self.procStat.nclients and self.procStat.nproc < self.nmax:
                #add a new process if not enough
                mp.Process(target=runChildProcess,args=(self.servsock,self.procStat,self.onClientComeEvent,isBaseProcess,self.timeout)).start()


def runChildProcess(servsock,procStat,clientComeEvent,isBaseProcess,acceptTimeout):
    #servsock,procStat,clientComeEvent,isBaseProcess,acceptTimeout = args
    #register new process
    procStat.nproc += 1
    childServ = ChildServer(servsock,procStat,clientComeEvent,isBaseProcess,acceptTimeout)
    childServ.workWithClients()



class ChildServer(Connection):

    def __init__(self,servsock,procStat,clientComeEvent,isBaseProcess,acceptTimeout,sendBufLen=2048, timeOut=30):
        super().__init__(sendBufLen, timeOut)
        self.talksock = None
        self.servsock = servsock
        self.procStat = procStat
        self.onClientComeEvent = clientComeEvent
        self.isBaseProcess = isBaseProcess
        self.acceptTimeout = acceptTimeout 
        #get id from client
        self.fillCommandDict()
        self.unblockNonBaseSockets()

    def fillCommandDict(self):
        self.commands.update({'echo':self.echo,
                              'time':self.time,
                              'quit':self.quit,
                              'download':self.sendFileTCP,
                              'upload':self.recvFileTCP})

   
   
    def unblockNonBaseSockets(self):
        #make socket unblocked
        timeout = self.acceptTimeout if not self.isBaseProcess else None             
        self.servsock.raw_sock.settimeout(timeout)
    
    def showProcStatus(self):
        print('proc status: ' + ('base' if self.isBaseProcess else 'temporary'),end='  ')

    def showStatusInfo(self):
        showSharedStatusInfo(self.procStat)
        self.showProcStatus()
        print(self.talksock.inetAddr,end=' ')
        print('is connected') 

    def showGoneClient(self):
        showSharedStatusInfo(self.procStat)
        self.showProcStatus()
        print(self.talksock.inetAddr,end=' ')
        print('gone')    

    def registerNewClient(self):
        try:
            sock, addr = self.servsock.raw_sock.accept()
            self.talksock = SockWrapper(raw_sock=sock,inetAddr=addr)
            #register in shared memory, rase onClientCome event
            self.procStat.nclients += 1
            #show client addr
            self.showStatusInfo()
            self.onClientComeEvent.set()
        except OSError as msg:
            #abort process if accept timeout
            #decrease process counter
            self.procStat.nproc -= 1
            print('timeout...',end='')
            #jmp to abort the process
            raise

       

    def workWithClients(self):
        try:
            while True:
                self.registerNewClient()
                self.clientCommandsHandling()
        except OSError:
            #abort this process (timeout exit only)
            print('broken')
            pass

    def echo(self,commandArgs):
        self.talksock.sendMsg(commandArgs)


    def time(self,commandArgs):
        self.talksock.sendMsg(time.asctime())

    def quit(self,commandArgs):
        self.talksock.raw_sock.shutdown(socket.SHUT_RDWR)
        self.talksock.raw_sock.close()


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
                
            except (OSError,FileWorkerCritError) as e:
                print(e)
                #decrease clients counter
                self.procStat.nclients -= 1
                #print that the client gone
                self.showGoneClient()
                break



if __name__ == "__main__":

    server = ParentServer("192.168.1.2","6000")
