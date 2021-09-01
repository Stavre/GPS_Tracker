import threading
import time
import re
from position import GNSS, position
import serial.tools.list_ports
import RPi.GPIO as GPIO

def atCommand(port, command, lock, endline="\r", removenewline=True, regex=".*", replace=None):
    if replace is None:
        replace = []
    rcv = '' #variable used to store command output
    for i in range(50): #try sending and receiving the command 50 times
        #time.sleep(0.1)
        rcv = ''
        w = str.encode(command + endline)  #encode command + endline in binary
        lock.acquire()  #lock for preventing concurrent access to serial port
        port.write(w)   #send command to modem via serial port
        rcv = port.read(size=1000).decode()   #read modem reply. since modem reply is less than 1000 bytes port.read waits until timeout
        lock.release()

        if "ERROR" not in rcv:  #check if modem reply was ERROR
            if removenewline is True:
                rcv = rcv.replace("\r", "").replace("\n", "").replace("\r\n", "") #removing newlines
            for a in replace:  #output processing. removing unwanted substrings
                rcv = rcv.replace(a[0], a[1])
            if re.match(regex, rcv):  #check if output matches regex
                return rcv
    #we didn't received expexted answear  after 50 tries. something must have happened
    print("Reply: " + rcv + " " + str(command))
    raise Exception(str("Error when executing command: " + command))


def sendSMS(port, number, message, lock):
    '''Sends message. AT command used: AT+CMGS= '''
    atCommand(port, 'AT+CMGS="' + number + '"', lock) #sending AT command
    atCommand(port, message, lock, endline=chr(26)) #sending message + AT command end character
    #for more details, go to https://www.diafaan.com/sms-tutorials/gsm-modem-tutorial/at-cmgs-text-mode/
    time.sleep(2)

def readSMS(port, pos, lock):
    '''Reads SMS message. Requires the message's position in memory. AT command used: AT+CMGR= .
    Returns a list containing the message content and the phone number of the message sender'''
    r = '.*\+CMGR: ".+?",".+?",".*?","\d+/\d+/\d+,\d+:\d+:\d+\+\d+".*'  #regex used for validating modem output
    rcv = atCommand(port, "AT+CMGR=" + str(pos), lock, regex=r, replace=[["OK", '']]) #sending command
    msg = re.split('.*\+CMGR: ".+?",".+?",".*?","\d+/\d+/\d+,\d+:\d+:\d+\+\d+"', rcv)[1] #extract message
    phoneNumber = rcv.split(",")[1].replace("\"", "") #extract phone number
    return [msg, phoneNumber]

def startingGPS(port, lock):
    '''Powers on GPS(warm restart) and GNSS.
    AT command used: AT+CGNSPWR=1 -> power on GNSS
    AT+CGPSRST=2 -> warm GPS restart'''
    return atCommand(port, "AT+CGNSPWR=1", lock) + atCommand(port, "AT+CGPSRST=2", lock)


def sendStartingGPS(port, phoneNumber, lock):
    '''Wrapper around startingGPS'''
    sendSMS(port, phoneNumber, startingGPS(port, lock), lock)


def stoppingGPS(port, lock):
    '''Powers off GPS and GNSS.
        AT commands used: AT+CGNSPWR=0 -> power off GNSS
        AT+CGPSRST=0 -> power off GPS'''
    return atCommand(port, "AT+CGNSPWR=0", lock) + atCommand(port, "AT+CGPSPWR=0", lock)

def sendStoppingGPS(port, phoneNumber, lock):
    '''Wrapper around stoppingGPS '''
    sendSMS(port, phoneNumber, stoppingGPS(port, lock), lock)

def statusGPS(port, lock):
    '''Returns GPS status. AT command used: AT+CGPSSTATUS?
    Possible values: Not Fixed, 2D Fixed, 3D Fixed, Unknown'''
    return atCommand(port, "AT+CGPSSTATUS?", lock)

def sendStatusGPS(port, phoneNumber, lock):
    '''Wrapper around statusGPS'''
    sendSMS(port, phoneNumber, statusGPS(port, lock), lock)

def mapLink(pos):
    '''Returns a google maps link based on a position passed as argument'''
    try:
        return "http://www.google.com/maps/place/" + str(pos.latitude) + "," + str(pos.longitude)
    except:
        return "No position found."

def sendMapLink(port, phoneNumber, alarm_args, lock):
    '''Sends map link. If there is no fixed position sends "No GPS signal."'''
    position = currentPos(port, alarm_args, lock)
    if position == 0:
        sendSMS(port, phoneNumber, "No GPS signal. Last known location is:", lock)
        sendSMS(port, phoneNumber, mapLink(alarm_args[1]),lock)
    else:
        sendSMS(port, phoneNumber, mapLink(position), lock)

def status(port, phoneNumber, alarm_args, lock):
    '''Sends basic info about device.'''
    report = ''
    #obtaining GPS power state
    report = report + atCommand(port, "AT+CGPSPWR?", lock).replace("+CGPSPWR", "GPS").replace("0", "OFF").replace("1", "ON")
    report = report + "\n" + "status locatie: "
    #obtaining position status
    report = report + atCommand(port, "AT+CGPSSTATUS?", lock).replace("+CGPSSTATUS:", "")
    report = report + "\n" + "Network "
    #obtaining network provider
    rcv = atCommand(port, "AT+CSPN?", lock)
    report = report + atCommand(port, "AT+CSPN?", lock).split(":")[1].split(",")[0] + "\n"
    #obtaining alarm status
    report = report + "\n" + "Alarm status  " + str(alarm_args[0])
    #sending report
    sendSMS(port, phoneNumber, report, lock)

def currentPos(port, alarm_args, lock):
    regex = "\+CGNSINF: .+,.+,.+,.+,.+,.+,.+,.+,.+,.*,.+,.+,.+,.*,.+,.+,.*,.*,.*,.*,.*"  #regex used for validating
    rcv = atCommand(port, "AT+CGPSPWR?", lock)
    if "0" in rcv:  #if GPS is off, turn on gps and GNSS
        atCommand(port, "AT+CGNSPWR=1", lock)
        atCommand(port, "AT+CGPSRST=2", lock)
        time.sleep(15)

    rcv = atCommand(port, "AT+CGPSSTATUS?", lock)
    if "Not Fix" in rcv or "Unknown" in rcv:  #if location is not fixed return 0
        return 0
    else:
        rcv = atCommand(port, "AT+CGNSINF", lock, regex=regex, replace=[["OK", ""]])  #get location
        rcv = rcv.split(":")[1].replace(" ", "")
        r = GNSS(rcv).getPosition() #get location object
        alarm_args[1] = alarm_args[2]
        alarm_args[2] = position(r.latitude, r.longitude) #set alarm position
        return alarm_args[2]

def startAlarm(port, var, phoneNumber, lock):
    '''Starts an infinite loop that checks if the distance between the current position
    and the alarm position is greater than 0.002. If so, calls the phone number'''
    referencePos = currentPos(port, alarm_args, lock) #get alarm position
    if referencePos == 0: #if true it means there is no GPS signal
        sendSMS(port, phoneNumber, "No GPS signal. Alarm not activated. ", lock)
        return 0
    else:
        sendSMS(port, phoneNumber, "Alarm activated.", lock)
        while True: #infinite loop
            lock.acquire() #lock to prevent concurent access
            val = var
            lock.release()
            if val[0] is False: #if true then the alarm was turned off
                sendSMS(port, phoneNumber, "Alarm deactivated", lock)
                return 0
            else:
                pos1 = currentPos(port, alarm_args, lock) #get current position
                if referencePos == 0 or pos1 == 0: #if true the GPS signal lost
                    #new thread that calls the phone number
                    task = threading.Thread(target=atCommand, args=(port, "ATD" + phoneNumber + ";", lock,))
                    task.start()
                    time.sleep(5)
                    #new thread that sends sms
                    task2 = threading.Thread(target=sendSMS, args=(port, phoneNumber, "No GPS signal." ,lock,))
                    task2.start()
                else:
                    lock.acquire()
                    val = var
                    lock.release()
                    if val[0]: #if alarm is on calculates distance between the two positions
                        if pos1.distance(referencePos) > 0.002: #if true the device is moving outside the intended range
                            task2 = threading.Thread(target=atCommand, args=(port, "ATD" + phoneNumber + ";", lock, ))
                            task2.start()
                            time.sleep(1)
                    else: #alarm was deactivated. sending confirmation
                        sendSMS(port, phoneNumber, "Alarm deactivated.", lock)
			time.sleep(2)
                        return 0
            begin = time.time()
            while time.time() - begin < 30: #non blocking wait loop
                lock.acquire()
                val = var
                lock.release()
                if val[0] is False: #if alarm is deactivated, send message
                    sendSMS(port, phoneNumber, "Alarm deactivated.", lock)
                    return 0


def interpretCommand(port, l, phoneNumbers, lock, password, alarm_args):
    '''Infinite loop for executing commands from l list'''
    while True:
        while len(l) > 0:
            task = ''
            lock.acquire()
            command = l.pop()
            lock.release()
            phoneNumber = command[1] #acquire phone number
            command = command[0].strip().replace("\n", "").replace("OK", "") #acquire command

            if phoneNumber not in phoneNumbers and "Logare=" in command: #authentification
                if command.split("=")[1] == password:
                    phoneNumbers.append(phoneNumber)
                    task = threading.Thread(target=sendSMS, args=(port, phoneNumber, "Sunteti logat.", lock,))
                    task.start()
            elif phoneNumber in phoneNumbers:
                if "Logare=" in command: #log in command when user is already logged in
                    task = threading.Thread(target=sendSMS, args=(port, phoneNumber, "Sunteti deja logat.", lock,))
                elif "Pornire GPS" == command: #turning on GPS
                    task = threading.Thread(target=sendStartingGPS, args=(port, phoneNumber, lock,))
                elif "Oprire GPS" == command:  #turning of GPS
                    task = threading.Thread(target=sendStoppingGPS, args=(port, phoneNumber, lock,))
                elif "Pozitie" == command:  #get current position
                    task = threading.Thread(target=sendMapLink, args=(port, phoneNumber,alarm_args, lock,))
                elif "Status GPS" == command: #GPS status
                    task = threading.Thread(target=sendStatusGPS, args=(port, phoneNumber, lock,))
                elif "Pornire Alarma" == command: #turn on alarm
                    alarm_args[0] = True
                    task = threading.Thread(target=startAlarm, args=(port, alarm_args, phoneNumber, lock,))
                elif "Oprire Alarma" == command: #turn off alarm
                    alarm_args[0] = False
                    task = threading.Thread(target=sendSMS, args=(port, phoneNumber, "comanda primita", lock, ))
                elif "Status" == command:  #get status
                    task = threading.Thread(target=status, args=(port, phoneNumber, alarm_args, lock,))
                else: #command not recognised
                    task = threading.Thread(target=sendSMS, args=(port, phoneNumber, "Comanda nu exista", lock, ))
                task.start()
            atCommand(port, "AT+CMGD=1,4", lock) #removes all received messages


def listenForActivity(port, l, lock):
    '''Infinite loop that listens for new messages(commands).'''
    while True:
        if port.in_waiting > 0: #if there are bytes in reading buffer read them
            lock.acquire()
            rcv = port.read(size=1000).decode().replace("OK", "").replace("\r", "").replace("\n", "")
            lock.release()
            if re.match('\+CMTI: ".*",\d+', rcv):  # check if the modem output matches the regex corresponding to a message
                msgPos = rcv.split(",")[1]
                l.append(readSMS(port, msgPos, lock)) #appends to the command list the command received
                print(l)

def startingModem(port, lock):
    '''AT commands for setting up modem'''
    atCommand(port, 'AT+CMEE=2', lock) #disable the use of error codes, all errors are reported as ERROR
    # Set SMSC   Add more providers
    atCommand(port, 'AT+CSCA="+40770000050"', lock) #set SMS center
    # Select Message format as Text mode
    atCommand(port, "AT+CMGF=1", lock)
    # Disable the Echo
    atCommand(port, 'ATE0', lock)
    sendSMS(port, "+40773791847", "Modem started successfully", lock)
    print("sent")


if __name__ == "__main__":
    #powering on the modem through raspberry pi zero's pins
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(7, GPIO.OUT)
    GPIO.output(7, GPIO.LOW)
    time.sleep(4)
    GPIO.output(7, GPIO.HIGH)
    time.sleep(15)
    GPIO.cleanup()

    # Enable Serial Communication with raspberry
    port = serial.Serial(port="/dev/ttyAMA0", baudrate=57600, timeout=2)
    lock = threading.Lock() #threading lock
    taskList = list() #command list
    phoneNumbers = ["+40773791847"] #phone numbers of the authenticated users
    time.sleep(15)
    startingModem(port, lock)
    password = "123" #pasword
    alarm_args = [False, '', ''] #alarm arguments first element is alarma status(on or off) 
				 #second element is last known position third element is used for storing current position
				 #if no GPS signal the third element is 0

    listen = threading.Thread(target=listenForActivity, args=(port, taskList, lock,))
    listen.start()
    interpretCommand(port, taskList, phoneNumbers, lock, password, alarm_args)
