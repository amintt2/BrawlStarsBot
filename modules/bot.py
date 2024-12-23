from time import time,sleep
from threading import Thread, Lock
from math import *
import pyautogui as py
import numpy as np
import random
from constants import Constants
"""
INITIALIZING: Initialize the bot
SEARCHING: Find the nearby bush to player
MOVING: Move to the selected bush
HIDING: Stop movement and hide in the bush
ATTACKING: Player will attack and activate gadget when enemy is nearby

"""
class BotState:
    INITIALIZING = 0
    SEARCHING = 1
    MOVING = 2
    HIDING = 3
    ATTACKING = 4

class Brawlbot:
    # In game tile width and height ratio with respect aspect ratio
    tile_w = 24
    tile_h = 17
    midpoint_offset = Constants.midpoint_offset

    # Map with sharp corners
    sharpCorner = Constants.sharpCorner
    # Either go to the closest bush to the player or the center
    centerOrder = Constants.centerOrder
    IGNORE_RADIUS = 0.5
    movement_screenshot = None
    screenshot = None
    INITIALIZING_SECONDS = 2
    results = []
    bushResult = []
    counter = 0
    direction = ["top","bottom","right","left"]
    current_bush = None
    last_player_pos = None
    last_closest_enemy = None
    border_size = 1
    stopped = True
    topleft = None
    avg_fps = 0
    enemy_move_key = None
    timeFactor = 1
    
    # time to move increase by 5% if maps have sharps corner
    if sharpCorner: timeFactor = 1.05

    def __init__(self,windowSize,offsets,speed,attack_range) -> None:
        self.lock = Lock()
        
        # Pre-calculate frequently used values
        self.speed = speed
        self.window_w = windowSize[0]
        self.window_h = windowSize[1]
        self.tile_w_ratio = self.window_w/self.tile_w
        self.tile_h_ratio = self.window_h/self.tile_h
        self.center_window = (self.window_w / 2, int((self.window_h / 2)+ self.midpoint_offset))

        # short range
        if attack_range >0 and attack_range <=4:
            range_multiplier = 1
            hide_multiplier = 1.3
        # medium range
        elif attack_range > 4 and attack_range <=7:
            range_multiplier = 0.85
            hide_multiplier = 1
        # long range
        else:  # attack_range > 7
            range_multiplier = 0.8
            hide_multiplier = 0.8
        
        # attack range in tiles
        self.alert_range = attack_range + 2
        self.attack_range = range_multiplier*attack_range
        self.gadget_range = 0.9*self.attack_range
        self.hide_attack_range = 3.5 # visible to enemy in the bush
        self.HIDINGTIME = hide_multiplier * 23
        
        self.timestamp = time()
        self.tileSize = round((round(self.window_w/self.tile_w)+round(self.window_h/self.tile_h))/2)
        self.state = BotState.INITIALIZING
        
        # offset
        self.offset_x = offsets[0]
        self.offset_y = offsets[1]

        #index
        self.player_index = 0
        self.bush_index = 1
        self.enemy_index = 2

    # translate a pixel position on a screenshot image to a pixel position on the screen.
    # pos = (x, y)
    # WARNING: if you move the window being captured after execution is started, this will
    # return incorrect coordinates, because the window position is only calculated in
    # the __init__ constructor.
    def get_screen_position(self, cordinate):
        """
        Apply bluestacks' window offset
        :param cordinate (tuple): cordinate in the cropped screenshot
        :return: cordinate with offset applied
        """
        return (cordinate[0] + self.offset_x, cordinate[1] + self.offset_y)
    
    # storm method
    def guess_storm_direction(self):
        """
        Predict in game storm direction through the player position.

        eg. if player is off centre to the right guess the storm direction
        to be on the right.

        :return: (List) list of x and y direction or list of empty string
        """
        # asign x and y direction
        x_direction = ""
        y_direction =  ""
        # if there is a detection
        if self.results:
            # there player detection
            if self.results[self.player_index]:
                x_border = (self.window_w/self.tile_w)*self.border_size
                y_border = (self.window_h/self.tile_h)*self.border_size
                # coordinate of the middle of the screen
                p0 = self.center_window
                # coordinate of the player
                p1 = self.results[self.player_index][0]
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
        """
        get movement key to move away from the storm

        :return: (List) list of movement keys or an empty list
        """
        x = ""
        y = ""
        # if there is detection
        if self.results:
            # if there is player detection
            if self.results[self.player_index]:
                # predict the storm direction
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
        """
        get the quadrant to select a bush to move to.

        :return: False (boolean)
                 (List) list of "quadrants"
        """
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
    def ordered_bush_by_distance(self, index):
        # our character is always in the center of the screen
        # if player position in result is empty
        # assume that player is in the middle of the screen
        if not(self.results[self.player_index]) or self.centerOrder:
            player_position = self.center_window
        else:
            player_position = self.results[self.player_index][0]
        def tile_distance(position):
            return sqrt(((position[0] - player_position[0])/(self.window_w/self.tile_w))**2 
                        + ((position[1] - player_position[1])/(self.window_h/self.tile_h))**2)
        # list of bush location is the in index 1 of results
        unfilteredResults = self.results[index]
        filteredResult = []
        # get quadrant
        quadrant = self.get_quadrant_bush()
        if quadrant:
            x_scale = self.window_w/3
            y_scale = self.window_h/3
            for x,y in unfilteredResults:
                # find bushes in the quadrant
                if ((x > quadrant[0][0]*x_scale and x <= quadrant[0][1]*x_scale)
                    and (y > quadrant[1][0]*y_scale and y <= quadrant[1][1]*y_scale)):
                    filteredResult.append((x,y))
            filteredResult.sort(key=tile_distance)
            if filteredResult:
                return filteredResult
        # if quadrant is False or filteredResult is empty
        if not(quadrant) or not(filteredResult):
            unfilteredResults.sort(key=tile_distance)
            return unfilteredResults
    
    def ordered_enemy_by_distance(self,index):
        # our character is always in the center of the screen
        # if player position in result is empty 
        # assume that player is in the middle of the screen
        if not(self.results[self.player_index]):
            player_position = self.center_window
        else:
            player_position = self.results[self.player_index][0]
        def tile_distance(position):
            return sqrt(((position[0] - player_position[0])/(self.window_w/self.tile_w))**2 
                        + ((position[1] - player_position[1])/(self.window_h/self.tile_h))**2)
        sortedResults = self.results[index]
        sortedResults.sort(key=tile_distance)
        return sortedResults
        
    def tile_distance(self, player_position, position):
        """
        Optimized tile distance calculation
        """
        dx = (position[0] - player_position[0])/self.tile_w_ratio
        dy = (position[1] - player_position[1])/self.tile_h_ratio
        return sqrt(dx*dx + dy*dy)
    
    def find_bush(self):
        """
        sort the bush by distance and assigned it to self.bushResult
        :return: True or False (boolean)
        """
        if self.results:
            self.bushResult = self.ordered_bush_by_distance(self.bush_index)
        if self.bushResult:
            return True
        else:
            return False
        

    def move_to_bush(self):
        """
        Optimized movement calculation
        """
        if not self.bushResult:
            return 0
            
        x, y = self.bushResult[0]
        player_pos = self.results[self.player_index][0] if self.results[self.player_index] else self.center_window
        
        # Calculate movement direction and distance in one pass
        dx = x - player_pos[0]
        dy = y - player_pos[1]
        
        # Determine movement keys
        keys = []
        if abs(dx) > 1:  # Add small threshold to prevent jitter
            keys.append('d' if dx > 0 else 'a')
        if abs(dy) > 1:  # Add small threshold to prevent jitter
            keys.append('s' if dy > 0 else 'w')
            
        # Press movement keys
        for key in keys:
            py.keyDown(key)
        
        # Calculate move time
        tileDistance = self.tile_distance(player_pos, (x,y))
        moveTime = (tileDistance/self.speed) * self.timeFactor
        
        print(f"Distance: {round(tileDistance,2)} tiles")
        return moveTime
    
    # enemy and attack method
    def attack(self):
        """
        Press the attack key
        """
        print("attacking enemy")
        attack_key = "e"
        py.press(attack_key)

    def gadget(self):
        """
        Press the gadget key
        """
        print("activate gadget")
        gadget_key = "f"
        py.press(gadget_key)

    def hold_movement_key(self,key,time):
        """
        Hold down a key for a certain amount time

        :param key (string): key to be hold
        :param time (float): time to hold the key
        """
        py.keyDown(key)
        sleep(time)
        py.keyUp(key)

    def storm_random_movement(self):
        """
        get movement keys and pick a random key to hold for one second
        """
        if self.storm_movement_key():
            move_keys = self.storm_movement_key()
        else:
            move_keys = ["w", "a", "s", "d"]
        random_move = random.choice(move_keys)
        self.hold_movement_key(random_move, 1)
    
    def stuck_random_movement(self):
        """
        get movement keys and pick a random key to hold for one second
        """
        move_keys = self.get_movement_key(self.bush_index)
        if not(move_keys):
            move_keys = ["w", "a", "s", "d"]
        random_move = random.choice(move_keys)
        self.hold_movement_key(random_move, 1)

    def get_movement_key(self, index):
        """
        Optimized movement key calculation
        """
        if not self.results or not self.results[index]:
            return []
            
        player_pos = self.results[self.player_index][0] if self.results[self.player_index] else self.center_window
        target_pos = self.enemyResults[0] if index == self.enemy_index else self.bushResult[0]
        
        dx = player_pos[0] - target_pos[0]
        dy = player_pos[1] - target_pos[1]
        
        keys = []
        if abs(dx) > 1:
            keys.append('d' if dx > 0 else 'a')
        if abs(dy) > 1:
            keys.append('s' if dy > 0 else 'w')
            
        return keys

    def enemy_random_movement(self):
        """
        Optimized enemy movement
        """
        if not self.enemy_move_key:
            move_keys = self.get_movement_key(self.enemy_index)
            if not move_keys:
                move_keys = random.choice(["w", "a", "s", "d"])
        else:
            move_keys = self.enemy_move_key

        # Combine movement and attack
        if isinstance(move_keys, list):
            for key in move_keys:
                py.keyDown(key)
        else:
            py.keyDown(move_keys)
            
        py.press("e", presses=2, interval=0.2)  # Reduced interval for faster attacks
        
        if isinstance(move_keys, list):
            for key in move_keys:
                py.keyUp(key)
        else:
            py.keyUp(move_keys)

    def enemy_distance(self):
        """
        Optimized enemy distance calculation
        """
        if not self.results or not self.results[self.enemy_index]:
            return None
            
        player_pos = self.results[self.player_index][0] if self.results[self.player_index] else self.center_window
        self.enemyResults = sorted(self.results[self.enemy_index], 
                                 key=lambda pos: self.tile_distance(player_pos, pos))
        
        return self.tile_distance(player_pos, self.enemyResults[0]) if self.enemyResults else None
    
    def is_enemy_in_range(self):
        """
        Check if enemy is in range of the player
        :return (boolean): True or False
        """
        enemyDistance = self.enemy_distance()
        if enemyDistance:
            # ranges in tiles
            if (enemyDistance > self.attack_range
                and enemyDistance <= self.alert_range):
                self.enemy_move_key = self.get_movement_key(self.enemy_index)
            elif (enemyDistance > self.gadget_range 
                  and enemyDistance <= self.attack_range):
                self.attack()
                return True
            elif enemyDistance <= self.gadget_range:
                self.gadget()
                self.attack()
                return True
        return False

    def is_enemy_close(self):
        """
        Check if enemy is visible in the bush
        :return (boolean): True or False
        """
        enemyDistance = self.enemy_distance()
        if enemyDistance:
            if enemyDistance <= self.hide_attack_range:
                self.gadget()
                self.attack()
                return True
        return False

    def is_player_damaged(self):
        """
        Check if player is damaged
        :return (boolean): True or False
        """
        if self.topleft:
            width = abs(self.topleft[0] - self.bottomright[0])
            height = abs(self.topleft[1] - self.bottomright[1])
            w1 = int(self.topleft[0] + width/3)
            w2 = int(self.topleft[0] + 2*(width/3))
            h = int(self.topleft[1] - height/2)
            try:
                if (py.pixelMatchesColor(w1,h,(204, 34, 34),tolerance=20)
                    or py.pixelMatchesColor(w2,h,(204, 34, 34),tolerance=20)):
                    print(f"player is damaged")
                    return True
            except OSError:
                pass
        return False
    
    def have_stopped_moving(self):
        """
        Check if player have stop moving
        :return (boolean): True or False
        """
        if self.results:
            if self.results[self.player_index]:
                player_pos = self.results[self.player_index][0]
                if self.last_player_pos is None:
                    self.last_player_pos = player_pos
                else:
                    # last player position is the same as the current
                    if self.last_player_pos == player_pos:
                        self.counter += 1
                        if self.counter == 2:
                            print("have stopped moving or stuck")
                            return True
                    else:
                        # reset counter
                        self.counter = 0
                    self.last_player_pos = player_pos
        return False

    def update_results(self,results):
        """
        update results from the detection
        """
        self.lock.acquire()
        self.results = results
        self.lock.release()
    
    def update_player(self,topleft,bottomright):
        """
        update player position for the is_player_damaged function
        """
        self.lock.acquire()
        self.topleft = topleft
        self.bottomright =bottomright
        self.lock.release()

    def update_screenshot(self, screenshot):
        """
        update screenshot
        """
        self.lock.acquire()
        self.screenshot = screenshot
        self.lock.release()

    def start(self):
        """
        start the bot
        """
        self.stopped = False
        self.loop_time = time()
        self.count = 0
        t = Thread(target=self.run)
        t.setDaemon(True)
        t.start()

    def release_movement_keys(self):
        """
        Release all movement keys (WASD)
        """
        for key in ['w', 'a', 's', 'd']:
            py.keyUp(key)

    def stop(self):
        """
        stop the bot
        """
        self.stopped = True
        # release all movement keys
        self.release_movement_keys()
        # reset last player position
        self.last_player_pos = None

    def run(self):
        """
        Optimized main loop with reduced lock contention and better state management
        """
        while not self.stopped:
            sleep(0.01)  # Reduced sleep time for faster response
            
            current_state = self.state  # Cache current state to reduce lock access
            current_time = time()
            
            if current_state == BotState.INITIALIZING:
                if current_time > self.timestamp + self.INITIALIZING_SECONDS:
                    with self.lock:
                        self.state = BotState.SEARCHING

            elif current_state == BotState.SEARCHING:
                # Check enemy first for faster response
                if self.is_enemy_in_range():
                    with self.lock:
                        self.state = BotState.ATTACKING
                    continue
                
                if self.find_bush():
                    print("found bush")
                    self.moveTime = self.move_to_bush()
                    with self.lock:
                        self.timestamp = current_time
                        self.state = BotState.MOVING
                else:
                    print("Cannot find bush")
                    self.storm_random_movement()

            elif current_state == BotState.MOVING:
                # Check conditions in order of priority
                if self.is_enemy_in_range():
                    with self.lock:
                        self.state = BotState.ATTACKING
                elif self.have_stopped_moving():
                    self.release_movement_keys()
                    self.stuck_random_movement()
                    with self.lock:
                        self.state = BotState.SEARCHING
                elif current_time > self.timestamp + self.moveTime:
                    self.release_movement_keys()
                    print("Hiding")
                    with self.lock:
                        self.timestamp = current_time
                        self.state = BotState.HIDING
                else:
                    sleep(0.1)  # Slightly reduced sleep time

            elif current_state == BotState.HIDING:
                # Check conditions in order of priority
                if self.is_player_damaged() or current_time > self.timestamp + self.HIDINGTIME:
                    print("Changing state to search")
                    with self.lock:
                        self.state = BotState.SEARCHING
                elif self.centerOrder and self.is_enemy_close():
                    print("Enemy is nearby")
                    with self.lock:
                        self.state = BotState.ATTACKING
                elif not self.centerOrder and self.is_enemy_in_range():
                    print("Enemy in range")
                    with self.lock:
                        self.state = BotState.ATTACKING

            elif current_state == BotState.ATTACKING:
                if self.is_enemy_in_range():
                    self.enemy_random_movement()
                else:
                    with self.lock:
                        self.state = BotState.SEARCHING
            
            # Update FPS with less frequent calculations
            if self.count % 10 == 0:  # Only update FPS every 10 iterations
                self.fps = 1 / (current_time - self.loop_time)
                self.avg_fps = (self.avg_fps * self.count + self.fps) / (self.count + 1)
            
            self.loop_time = current_time
            self.count += 1