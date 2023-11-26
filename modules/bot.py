from time import time,sleep
from threading import Thread, Lock
from math import *
import pydirectinput as py
import pyautogui
import numpy as np
import random
from constants import Constants

class BotState:
    INITIALIZING = 0
    # starting the bot
    
    SEARCHING = 1
    """
    searching for bush to hide
    will try to search for the closest bush to the midpoint
    """
    
    MOVING = 2
    """
    Move to the selected bush.
    Brawler's tile speed and tile distance is used to calculate the time it takes
    and it will know when "player" is stuck on obstacle (using opencv to calculate the 
    similarity of previous screenshot and the current screenshot )
    
    if enemy or storm is near the path it will try to search for another bush
    """
    HIDING = 3
    """
    when "player" is inside the bush 
    if enemy is close
    attack depends on brawler range (short,medium,long) 
    and distance to enemy (in tiles)
    """
    ATTACKING = 4
    
class Brawlbot:
    # In game tile width and height ratio with respect aspect ratio
    tile_w = 24
    tile_h = 17
    midpoint_offset = Constants.midpoint_offset

    # Map with sharp corners
    sharpCorner = Constants.sharpCorner
    # Either go to the closest bush to the player or to the center
    centerOrder = Constants.centerOrder
    MOVEMENT_STOPPED_THRESHOLD = 0.95
    HIDINGTIME = 10
    IGNORE_RADIUS = 0.5
    movement_screenshot = None
    screenshot = None
    INITIALIZING_SECONDS = 2
    results = []
    bushResult = []
    counter = 0
    direction = ["top","bottom","right","left"]
    current_bush = None
    timeFactor = 1
    last_player_pos = None
    last_closest_enemy = None
    border_size = 1.2
    stopped = True
    topleft = None
    avg_fps = 0


    if sharpCorner:
        # time to move increase by 5% if maps have sharps corner
        timeFactor = 1.05

    def __init__(self,windowSize,offsets,speed,attack_range) -> None:
        self.lock = Lock()
        # "brawler" chracteristic
        self.speed = speed
        # attack range in tiles
        self.attack_range = 0.8*attack_range
        self.gadget_range = 0.8*self.attack_range
        self.hide_attack_range = 3.5 # visible to enemy in the bush

        self.timestamp = time()
        self.window_w = windowSize[0]
        self.window_h = windowSize[1]
        self.center_window = (self.window_w / 2, int((self.window_h / 2)+ self.midpoint_offset))

        # tile size of the game
        # depended on the dimension of the game
        self.tileSize = round((round(self.window_w/self.tile_w)+round(self.window_h/self.tile_h))/2)
        self.state = BotState.INITIALIZING
        
        # offset
        self.offset_x = offsets[0]
        self.offset_y = offsets[1]

    # translate a pixel position on a screenshot image to a pixel position on the screen.
    # pos = (x, y)
    # WARNING: if you move the window being captured after execution is started, this will
    # return incorrect coordinates, because the window position is only calculated in
    # the __init__ constructor.
    def get_screen_position(self, pos):
        return (pos[0] + self.offset_x, pos[1] + self.offset_y)
    
    # storm method

    def guess_storm_direction(self):
        # asign x and y direction
        x_direction = ""
        y_direction =  ""
        if self.results:
            if self.results[0]:
                x_border = (self.window_w/self.tile_w)*self.border_size
                y_border = (self.window_h/self.tile_h)*self.border_size
                # coordinate of the middle of the screen
                p0 = self.center_window
                # coordinate of the player
                p1 = self.results[0][0]
                # get the difference between centre and the player
                xDiff , yDiff = tuple(np.subtract(p1, p0))
                # player is on the right
                if xDiff>x_border:
                    x_direction = self.direction[2]
                # player is on the left
                elif xDiff<-x_border:
                    x_direction = self.direction[3]
                # player is on the bottom
                if yDiff>y_border:
                    y_direction = self.direction[1]
                # player is on the top
                elif yDiff<-y_border:
                    y_direction = self.direction[0]
                return [x_direction,y_direction]
            else:
                return 2*[""]
        else:
            return 2*[""]
    
    def storm_movement_key(self):
        x = ""
        y = ""
        if self.results:
            if self.results[0]:
                direction = self.guess_storm_direction()
                if direction[0] == self.direction[2]:
                    x = "a"
                # player is on the left
                elif direction[0] == self.direction[3]:
                    x = "d"
                # player is on the bottom
                if direction[1] == self.direction[1]:
                    y = "w"
                # player is on the top
                elif direction[1] == self.direction[0]:
                    y = "s"
        if [x,y] == ["",""]:
            return []
        else:
            return [x,y]

    def get_quadrant_bush(self):
        length = 0
        direction = self.guess_storm_direction()
        for i in range(len(direction)):
            if len(direction[i]) > 0:
                length += 1
                index = i
        if length == 0:
            return False
        elif length == 1:
            single_direction = direction[index]
            # top
            if single_direction == self.direction[0]:
                return [[0,3],[2,3]]
            # bottom
            elif single_direction == self.direction[1]:
                return [[0,3],[0,1]]
            # right
            elif single_direction == self.direction[2]:
                return [[0,1],[0,3]]
            # left
            elif single_direction == self.direction[3]:
                return [[2,3],[0,3]]
        elif length == 2:
            # top right
            if direction == [self.direction[0],self.direction[2]]:
                return [[0,2],[1,3]]
            # top left
            elif direction == [self.direction[0],self.direction[3]]:
                return [[1,3],[1,3]]
            # bottom right
            elif direction == [self.direction[1],self.direction[2]]:
                return [[0,2],[0,2]]
            # bottom left
            elif direction == [self.direction[1],self.direction[3]]:
                return [[1,3],[0,2]]
        
    # bush method

    def targets_ordered_by_distance(self, results, index):
        # our character is always in the center of the screen
        # if player position in result is empty
        # assume that player is in the middle of the screen
        if not(results[0]) or self.centerOrder :
            player_pos = self.center_window
        else:
            player_pos = results[0][0]
        # searched "python order points by distance from point"
        # simply uses the pythagorean theorem
        # https://stackoverflow.com/a/30636138/4655368
        def tile_distance(pos):
            return sqrt(((pos[0] - player_pos[0])/(self.window_w/self.tile_w))**2 + ((pos[1] - player_pos[1])/(self.window_h/self.tile_h))**2)
        # list of bush location is the in index 1 of results
        unfilteredResults = results[index]
        filteredResult = []
        quadrant = self.get_quadrant_bush()
        if quadrant:
            x_scale = self.window_w/3
            y_scale = self.window_h/3
            for x,y in unfilteredResults:
                if ((x > quadrant[0][0]*x_scale and x <= quadrant[0][1]*x_scale)
                    and (y > quadrant[1][0]*y_scale and y <= quadrant[1][1]*y_scale)):
                    filteredResult.append((x,y))
            filteredResult.sort(key=tile_distance)
            if filteredResult:
                return filteredResult
            
        if not(quadrant) or not(filteredResult):
            unfilteredResults.sort(key=tile_distance)
            return unfilteredResults

    def tile_distance(self,player_pos,pos):
        return sqrt(((pos[0] - player_pos[0])/(self.window_w/self.tile_w))**2 + ((pos[1] - player_pos[1])/(self.window_h/self.tile_h))**2)
    
    def find_bush(self):
        if self.results:
            self.bushResult = self.targets_ordered_by_distance(self.results,1)
        if self.bushResult:
            return True
        else:
            return False
        

    def move_to_bush(self):
        #get the nearest bush to the player
        if self.bushResult:
            x,y = self.bushResult[0]
            if not(self.results[0]) or self.centerOrder:
                player_pos = self.center_window
            else:
                player_pos = self.results[0][0]
            tileDistance = self.tile_distance(player_pos,(x,y))
            x,y = self.get_screen_position((x,y))
            py.mouseDown(button=Constants.movement_key,x=x, y=y)
            moveTime = tileDistance/self.speed
            moveTime = moveTime * self.timeFactor
            print(f"Distance: {round(tileDistance,2)} tiles")
            return moveTime
    
    # enemy and attack method
    def attack(self):
        py.press("e")

    def gadget(self):
        py.press("f")

    def hold_movement_key(self,key,time):
        py.keyDown(key)
        sleep(time)
        py.keyUp(key)

    def storm_random_movement(self):
        if self.storm_movement_key():
            move_keys = self.storm_movement_key()
        else:
            move_keys = ["w", "a", "s", "d"]
        random_move = random.choice(move_keys)
        self.hold_movement_key(random_move,1)
    
    def random_movement(self):
        move_keys = ["w", "a", "s", "d"]
        random_move = random.choice(move_keys)
        self.hold_movement_key(random_move,1)

    def get_enemy_direction(self):
        # asign x and y direction
        x_direction = ""
        y_direction = ""

        if self.results:
            if self.results[0]:
                player_pos = self.results[0][0]
            # if player position in result is empty
            # assume that player is in the middle of the screen
            else:
                player_pos = self.center_window
            
            if self.results[2]:
                p1 = player_pos
                p0 = self.enemyResults[0]
                xDiff , yDiff = tuple(np.subtract(p1, p0))
                # enemy is on the right
                if xDiff>0:
                    x_direction = self.direction[2]
                # enemy is on the left
                elif xDiff<0:
                    x_direction = self.direction[3]
                # enemy is on the bottom
                if yDiff>0:
                    y_direction = self.direction[1]
                # enemy is on the top
                elif yDiff<0:
                    y_direction = self.direction[0]
        
        return [x_direction,y_direction]
    
    def enemy_movement_key(self):
        x = ""
        y = ""
        if self.results:
            if self.results[0]:
                direction = self.get_enemy_direction()
                if direction[0] == self.direction[2]:
                    x = "d"
                elif direction[0] == self.direction[3]:
                    x = "a"
                if direction[1] == self.direction[1]:
                    y = "s"
                elif direction[1] == self.direction[0]:
                    y = "w"
        if [x,y] == ["",""]:
            return []
        else:
            return [x,y]
        
    def enemy_random_movement(self):
        if self.enemy_movement_key():
            move_keys = self.enemy_movement_key()
        else:
            move_keys = ["w", "a", "s", "d"]
        random_move = random.choice(move_keys)
        py.keyDown(random_move)
        self.attack()
        sleep(0.1)
        self.attack()
        sleep(0.1)
        py.keyUp(random_move)
    
    def enemy_distance(self):
        if self.results:
            # player coordinate
            if self.results[0]:
                player_pos = self.results[0][0]
            # if player position in result is empty
            # assume that player is in the middle of the screen
            else:
                player_pos = self.center_window
            # enemy coordinate
            if self.results[2]:
                enemyResults = self.targets_ordered_by_distance(self.results,2)
                self.enemyResults = [e for e in enemyResults if self.tile_distance(player_pos,e) > self.IGNORE_RADIUS]
                if self.enemyResults:
                    enemyDistance = self.tile_distance(player_pos,self.enemyResults[0])
                    # print(f"Closest enemy: {round(enemyDistance,2)} tiles")
                    return enemyDistance
        return None
    
    def is_enemy_in_range(self):
        """
        return boolen, notified bot if enemy is close to player
        """
        enemyDistance = self.enemy_distance()
        if enemyDistance:
            # ranges in tiles
            if enemyDistance > self.gadget_range and enemyDistance <= self.attack_range:
                self.attack()
                return True
            elif enemyDistance <= self.gadget_range:
                self.gadget()
                self.attack()
                return True
        return False

    def is_enemy_close(self):
        enemyDistance = self.enemy_distance()
        if enemyDistance:
            if enemyDistance <= self.hide_attack_range:
                self.gadget()
                self.attack()
                return True
        return False

    def is_player_damaged(self):
        if self.topleft:
            width = abs(self.topleft[0] - self.bottomright[0])
            height = abs(self.topleft[1] - self.bottomright[1])
            w1 = int(self.topleft[0] + width/3)
            w2 = int(self.topleft[0] + 2*(width/3))
            h = int(self.topleft[1] - height/2)
            try:
                if (pyautogui.pixelMatchesColor(w1,h,(204, 34, 34),tolerance=20)
                    or pyautogui.pixelMatchesColor(w2,h,(204, 34, 34),tolerance=20)):
                    print(f"player is damaged")
                    return True
            except OSError:
                pass
        return False
    
    def update_results(self,results):
        self.lock.acquire()
        self.results = results
        self.lock.release()
    
    def update_player(self,topleft,bottomright):
        self.lock.acquire()
        self.topleft = topleft
        self.bottomright =bottomright
        self.lock.release()

    def have_stopped_moving(self):
        if self.results:
            if self.results[0]:
                player_pos = self.results[0][0]
                if self.last_player_pos is None:
                    self.last_player_pos = player_pos
                else:
                    if self.last_player_pos == player_pos:
                        print("have stopped moving or stuck")
                        return True
                    self.last_player_pos = player_pos
        return False
        
    def update_screenshot(self, screenshot):
        self.lock.acquire()
        self.screenshot = screenshot
        self.lock.release()

    def start(self):
        self.stopped = False
        self.loop_time = time()
        self.count = 0
        t = Thread(target=self.run)
        t.setDaemon(True)
        t.start()

    def stop(self):
        self.stopped = True
        # reset last player position
        self.last_player_pos = None

    def run(self):
        while not self.stopped:
            sleep(0.01)
            if self.state == BotState.INITIALIZING:
                # do no bot actions until the startup waiting period is complete
                if time() > self.timestamp + self.INITIALIZING_SECONDS:
                    # start searching when the waiting period is over
                    self.lock.acquire()
                    self.state = BotState.SEARCHING
                    self.lock.release()

            elif self.state == BotState.SEARCHING:
                success = self.find_bush()
                #if bush is detected
                if success:
                    print("found bush")
                    self.lock.acquire()
                    self.timestamp = time()
                    self.state = BotState.MOVING
                    self.moveTime = self.move_to_bush()
                    self.lock.release()
                #bus is not detected
                else:
                    print("Cannot find bush")
                    self.storm_random_movement()
                    self.counter+=1
                
                if self.is_enemy_in_range():
                        self.lock.acquire()
                        self.state = BotState.ATTACKING
                        self.lock.release()

            elif self.state == BotState.MOVING:
                # when player is moving check if player is stuck
                if time() < self.timestamp + self.moveTime:
                    if not self.have_stopped_moving():
                        # wait a short time to allow for the character position to change
                        sleep(0.4)
                    #if player is stuck
                    else:
                        # cancel moving
                        py.mouseUp(button = Constants.movement_key)
                        self.random_movement()
                        self.lock.acquire()
                        # and search for bush again
                        self.state = BotState.SEARCHING
                        self.lock.release()
                    if self.is_enemy_in_range():
                        self.lock.acquire()
                        self.state = BotState.ATTACKING
                        self.lock.release()

                # player successfully travel to the selected bush
                else:
                    py.mouseUp(button = Constants.movement_key)
                    print("Hiding")
                    self.lock.acquire()
                    # change state to hiding
                    self.timestamp = time()
                    self.state = BotState.HIDING
                    self.lock.release()
                    
            elif self.state == BotState.HIDING:
                if self.is_player_damaged():
                    print("Changing state to search")
                    self.lock.acquire()
                    self.state = BotState.SEARCHING
                    self.lock.release()
                
                if self.is_enemy_close():
                    print("Enemy is nearby")
                    self.lock.acquire()
                    self.state = BotState.ATTACKING
                    self.lock.release()
            
            elif self.state == BotState.ATTACKING:
                if self.is_enemy_in_range():
                    print("attacking enemy")
                    self.enemy_random_movement()
                else:
                    self.lock.acquire()
                    self.state = BotState.SEARCHING
                    self.lock.release()
                    
            
            self.fps = (1 / (time() - self.loop_time))
            self.loop_time = time()
            self.count += 1
            if self.count == 1:
                self.avg_fps = self.fps
            else:
                self.avg_fps = (self.avg_fps*self.count+self.fps)/(self.count + 1)