import math

class GNSS():
    ''' Receives NMEA position as string and splits it into data'''
    def __init__(self, string):
        self.string = string.split(",")
        self.gnss_run_status = self.string[0]
        self.Fix_status = self.string[1]
        self.UTC_date_Time = self.string[2]
        self.Latitude = self.string[3]
        self.Longitude = self.string[4]
        self.MSL_Altitude = self.string[5] #unit of measurement: m
        self.Speed_Over_Ground = self.string[6]  #unit of measurement: Km / hour
        self.Course_Over_Ground_degrees = self.string[7]   #unit of measurement: degrees     [0, 360.00]
        self.Fix_Mode = self.string[8] # not used yet
        self.Reserved1 = self.string[9] # not used yet
        self.HDOP = self.string[10] # not used yet
        self.PDOP = self.string[11] # not used yet
        self.VDOP = self.string[12] # not used yet
        self.Reserved2 = self.string[13] # not used yet
        self.GPS_Satellites_in_View = self.string[14]
        self.GNSS_Satellites_Used = self.string[15]
        self.GLONASS_Satellites_in_View = self.string[16]
        self.Reserved3 = self.string[17] # not used yet
        self.CN0_max = self.string[18] # not used yet
        self.HPA = self.string[19] # not used yet
        self.VPA = self.string[20] # not used yet

    def getPosition(self):
        return position(self.Latitude, self.Longitude)

class position():
    '''Simple class consisting of longitude and latitude. Later current speed and course will be added.'''
    def __init__(self, latitude, longitude):
        self.latitude = float(latitude)
        self.longitude = float(longitude)

    def distance(self, pos):
        '''Get distance between two positions. uses pythagorean theorem'''
        R = 6.371 #earth's radius in km
        x = (pos.longitude - self.longitude)*math.cos((self.latitude + pos.latitude) / 2)
        y = pos.latitude - self.latitude
        distance = math.sqrt(x**2 + y**2) * R
        return distance



