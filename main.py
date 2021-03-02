import tcod as libtcod
import math
import textwrap
import shelve
import time
import random
from playsound import playsound
import copy

#actual size of the window
SCREEN_WIDTH = 80
SCREEN_HEIGHT = 40
#sizes and coordinates relevant for the GUI
BAR_WIDTH = 20
PANEL_HEIGHT = 7
PANEL_Y = SCREEN_HEIGHT - PANEL_HEIGHT

MSG_X = BAR_WIDTH + 2
MSG_WIDTH = SCREEN_WIDTH - BAR_WIDTH - 2
MSG_HEIGHT = PANEL_HEIGHT - 2

INVENTORY_WIDTH = 50

#size of the map
MAP_WIDTH = 80
MAP_HEIGHT = 30

#parameters for dungeon generator
ROOM_MAX_SIZE = 10
ROOM_MIN_SIZE = 6

rooms=[]

FOV_ALGO = 2  #default FOV algorithm
FOV_LIGHT_WALLS = True  #light walls or not
TORCH_RADIUS = 15
HEAL_AMOUNT=10

#experience and level-ups
LEVEL_UP_BASE = 200
LEVEL_UP_FACTOR = 150

LIMIT_FPS = 20  #20 frames-per-second maximum


color_dark_wall = libtcod.Color(50, 50, 50)
color_light_wall = libtcod.Color(120,110,100)
color_dark_ground = libtcod.Color(30, 30, 40)
color_light_ground = libtcod.Color(60,55,50)

def clamp(minimum, x, maximum):
    return max(minimum, min(x, maximum))

def new_game():
    global player, inventory, game_msgs, game_state, dungeon_level

    name="Seikkailija"
        #create object representing the player
    fighter_component = Fighter(hp=30, hunger=20, defense=2, power=5, xp=0, death_function=player_death)
    player = Object(0, 0, '@', name, libtcod.white, blocks=True, fighter=fighter_component, player=True)

    player.level = 1

    #generate map (at this point it's not drawn to the screen)
    dungeon_level = 1
    make_map()

    game_state = 'playing'
    inventory = []

    #create the list of game messages and their colors, starts empty
    game_msgs = []

    #a warm welcoming message!
    initialize_fov()

    # -*- coding: utf-8 -*-
    message("Astut pimeään tyrmään, tavoitteenasi löytää Urho Kekkosen kadonnut muumioitunut pää.")

def initialize_fov():
    libtcod.console_clear(con)
    global fov_recompute, fov_map
    fov_recompute = True

    #create the FOV map, according to the generated map
    fov_map = libtcod.map_new(MAP_WIDTH, MAP_HEIGHT)
    for y in range(MAP_HEIGHT):
        for x in range(MAP_WIDTH):
            libtcod.map_set_properties(fov_map, x, y, not map[x][y].block_sight, not map[x][y].blocked)

def save_game():
    #open a new empty shelve (possibly overwriting an old one) to write the game data
    file = shelve.open('savegame', 'n')
    file['map'] = map
    file['objects'] = objects
    file['player_index'] = objects.index(player)  #index of player in objects list
    file['inventory'] = inventory
    file['game_msgs'] = game_msgs
    file['game_state'] = game_state
    file['stairs_index'] = objects.index(stairs)
    file['dungeon_level'] = dungeon_level

    file.close()

def load_game():
    #open the previously saved shelve and load the game data
    global map, objects, player, inventory, game_msgs, game_state,stairs,dungeon_level

    file = shelve.open('savegame', 'r')
    map = file['map']
    objects = file['objects']
    player = objects[file['player_index']]  #get index of player in objects list and access it
    inventory = file['inventory']
    game_msgs = file['game_msgs']
    game_state = file['game_state']
    stairs=objects[file['stairs_index']]
    dungeon_level = file['dungeon_level']


    file.close()

    initialize_fov()


def check_level_up():
    #see if the player's experience is enough to level-up
    level_up_xp = LEVEL_UP_BASE + player.level * LEVEL_UP_FACTOR
    if player.fighter.xp >= level_up_xp:
        #it is! level up
        player.level += 1
        player.fighter.xp -= level_up_xp
        playsound('assets/sounds/levelup.wav')
        message('Tunnet kokemuksesi karttuneen! Saavutat tason ' + str(player.level) + '!', libtcod.yellow)
        choice=libtcod.random_get_int(0, 0, 2)
        if choice == 0:
            player.fighter.base_max_hp += 20
            player.fighter.hp += 20
            message('Elinvoimasi kasvaa!', libtcod.yellow)
        elif choice == 1:
            player.fighter.base_power += 1
            message('Voimasi kasvavat!', libtcod.yellow)
        elif choice == 2:
            player.fighter.base_defense += 1
            message('Puolustuksesi kasvaa!', libtcod.yellow)


class Point:
    def __init__(self,x,y):
        self.x=x
        self.y=y

class Tile:
    #a tile of the map and its properties
    def __init__(self, blocked, block_sight = None,char=" ",color=libtcod.gray,bgcolor=color_light_ground):
        self.blocked = blocked
        self.char=char
        self.color=color
        self.bgcolor=bgcolor

        #all tiles start unexplored
        self.explored = False

        #by default, if a tile is blocked, it also blocks sight
        if block_sight is None: block_sight = blocked
        self.block_sight = block_sight

class Rect:
    #a rectangle on the map. used to characterize a room.
    def __init__(self, x, y, w, h):
        self.x1 = x
        self.y1 = y
        self.x2 = x + w
        self.y2 = y + h

    def center(self):
        center_x = (self.x1 + self.x2) / 2
        center_y = (self.y1 + self.y2) / 2
        return (int(center_x), int(center_y))

    def intersect(self, other):
        #returns true if this rectangle intersects with another one
        return (self.x1 <= other.x2 and self.x2 >= other.x1 and
                self.y1 <= other.y2 and self.y2 >= other.y1)

class Object:
    #this is a generic object: the player, a monster, an item, the stairs...
    #it's always represented by a character on screen.
    def __init__(self, x, y, char, name, color, blocks=False, actions={}, fighter=None, ai=None, item=None, equipment=None, player=False):
        self.name = name
        self.blocks = blocks
        self.x = x
        self.y = y
        self.char = char
        self.color = color
        self.player = player

        self.actions=actions

        self.fighter = fighter
        if self.fighter:  #let the fighter component know who owns it
            self.fighter.owner = self

        self.ai = ai
        if self.ai:  #let the AI component know who owns it
            self.ai.owner = self

        self.item = item
        if self.item:  #let the Item component know who owns it
            self.item.owner = self

        self.equipment = equipment
        if self.equipment:  #let the Equipment component know who owns it
            self.equipment.owner = self
            #there must be an Item component for the Equipment component to work properly
            self.item = Item()
            self.item.owner = self

    def move(self, dx, dy):
        #move by the given amount, if the destination is not blocked
        blocking=is_blocked(self.x + dx, self.y + dy)
        if blocking==None:
            self.x += dx
            self.y += dy
            #self.send_to_fore()
            bump = get_object(self.x + dx, self.y + dy)
            if bump!=None and "bump" in bump.actions:
                bump.actions[bump](self)
            return True
        else:
            if blocking!=True and "bump" in blocking.actions:
                blocking.actions["bump"](self)
            return False
    def draw(self):
        #only show if it's visible to the player
        if libtcod.map_is_in_fov(fov_map, self.x, self.y):
            #set the color and then draw the character that represents this object at its position
            libtcod.console_set_default_foreground(con, self.color)
            libtcod.console_put_char(con, self.x, self.y, self.char, libtcod.BKGND_NONE)

    def clear(self):
        #erase the character that represents this object
        libtcod.console_put_char(con, self.x, self.y, ' ', libtcod.BKGND_NONE)

    def move_towards(self, target_x, target_y):
        #vector from this object to the target, and distance
        dx = target_x - self.x
        dy = target_y - self.y
        distance = math.sqrt(dx ** 2 + dy ** 2)

        #normalize it to length 1 (preserving direction), then round it and
        #convert to integer so the movement is restricted to the map grid
        dx = int(round(dx / distance))
        dy = int(round(dy / distance))
        self.move(dx, dy)

    def distance_to(self, other):
        #return the distance to another object
        dx = other.x - self.x
        dy = other.y - self.y
        return math.sqrt(dx ** 2 + dy ** 2)

    def send_to_back(self):
        #This code bugs, remember to fix it before using.
        global objects
        objects.remove(self)
        objects.insert(0, self)

    def send_to_fore(self):
        global objects
        objects.remove(self)
        objects.append(self)
class Fighter:
    #combat-related properties and methods (monster, player, NPC).
    def __init__(self, hp, hunger, defense, power, xp, death_function=None, fight_messages=["@1 kamppailee @2a vastaan"]):
        self.xp = xp
        self.death_function = death_function
        self.base_max_hp = hp
        self.hp = hp
        self.base_max_hunger = hunger
        self.hunger = hunger
        self.base_defense = defense
        self.base_power = power
        self.fight_messages=fight_messages
    def take_damage(self, damage,attacker=None):
        if self.hunger > 0:
            self.hunger -= 2
        #apply damage if possible
        if damage > 0:
            self.hp -= damage
            #check for death. if there's a death function, call it
            if self.hp <= 0:
                function = self.death_function
                if function is not None:
                    function(self.owner)
                    playsound('assets/sounds/death.wav')
                if attacker is not None:
                    attacker.xp += self.xp
    def attack(self, target):
        #a simple formula for attack damage
        damage = self.power - target.fighter.defense
        colorr=[libtcod.red,libtcod.green]
        if self.owner.player:
            colorr=[libtcod.green,libtcod.red]
            playsound('assets/sounds/playerhit.wav')
        else:
            playsound('assets/sounds/enemyhit.wav')
        if damage > 0:
            #make the target take some damage
            message(random.choice(self.fight_messages).replace("@1",self.owner.name).replace("@2",target.name), colorr[0],self.owner.x,self.owner.y)
            target.fighter.take_damage(damage,self)
        else:
            message(random.choice(self.fight_messages).replace("@1",self.owner.name).replace("@2",target.name) + ', ilman vaikutusta!', colorr[1],self.owner.x,self.owner.y)

    def heal(self, amount):
        #heal by the given amount, without going over the maximum
        self.hp += amount
        if self.hp > self.max_hp:
            self.hp = self.max_hp
    def feed(self, amount):
        #feed by the given amount, without going over the maximum
        self.hunger += amount
        if self.hunger > self.base_max_hunger:
            self.hunger = self.base_max_hunger
    @property
    def power(self):
        bonus = sum(equipment.power_bonus for equipment in get_all_equipped(self.owner))
        return self.base_power + bonus
    @property
    def defense(self):  #return actual defense, by summing up the bonuses from all equipped items
        bonus = sum(equipment.defense_bonus for equipment in get_all_equipped(self.owner))
        return self.base_defense + bonus
    @property
    def max_hp(self):  #return actual max_hp, by summing up the bonuses from all equipped items
        bonus = sum(equipment.max_hp_bonus for equipment in get_all_equipped(self.owner))
        return self.base_max_hp + bonus

class NoobMonster:
    #AI for a basic monster.
    def take_turn(self):
        monster=self.owner
        move=True
        for object in objects:
            if object!=monster and hasattr(object,"fighter") and object.fighter is not None and monster.distance_to(object) < 2 and object.fighter.hp>0:
                monster.fighter.attack(object)
                move=False
        if move:
            sx=random.randint(-1,1)
            sy=random.randint(-1,1)
            monster.move(sx,sy)

class BasicMonster:
    def __init__(self,period=1):
        self.period=period
        self.tick=0
    #AI for a basic monster.
    def take_turn(self):
        self.tick+=1
        moved=False
        monster = self.owner
        if self.tick%self.period==0:
            #a basic monster takes its turn. If you can see it, it can see you
            if libtcod.map_is_in_fov(fov_map, monster.x, monster.y):

                #move towards player if far away
                if monster.distance_to(player) >= 2:
                    moved=monster.move_towards(player.x, player.y)

                #close enough, attack! (if the player is still alive.)
        if not moved and player.fighter.hp > 0 and monster.distance_to(player) < 2:
            monster.fighter.attack(player)
class AdvancedMonster:
    def __init__(self,period=1):
        self.period=period
        self.tick=0
    def take_turn(self):
        self.tick+=1
        moved=False
        monster = self.owner
        if self.tick%self.period==0:
            try:
                if self.path==None:
                    self.path = libtcod.path_new_using_map(path_map)
            except:
                self.path = libtcod.path_new_using_map(path_map)
            success=libtcod.path_compute(self.path, monster.x, monster.y, player.x, player.y)
            stepx,stepy=libtcod.path_walk(self.path,True)
            #move towards player if far away
            if monster.distance_to(player) >= 2 and success:
                moved=monster.move(stepx-monster.x,stepy-monster.y)
            #close enough, attack! (if the player is still alive.)
        for object in objects:
            if object!=monster and hasattr(object,"fighter") and object.fighter is not None and monster.distance_to(object) < 2 and object.fighter.hp>0 and not (object==player and moved):
                monster.fighter.attack(object)

class Wandering:
    def __init__(self):
        self.success=False
    def randomize_target(self):
        blocked=True
        room = random.choice(rooms)
        while blocked is not None:
            x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
            y = libtcod.random_get_int(0, room.y1+1, room.y2-1)
            blocked=is_blocked(x,y)
            self.target_x=y
            self.target_y=x
        self.recalculate()

    def recalculate(self):
        monster = self.owner
        self.success=libtcod.path_compute(self.path, monster.x, monster.y, self.target_x, self.target_y)


    def take_turn(self):
        monster = self.owner
        try:
            if self.path==None:
                self.path = libtcod.path_new_using_map(copy.deepcopy(path_map))
        except:
            self.path = libtcod.path_new_using_map(copy.deepcopy(path_map))

        try:
            if self.target_x is None or self.target_y is None:
                self.randomize_target()
        except:
            self.randomize_target()

        stepx,stepy=0,0
        moved=False
        if monster.distance_to(Point(self.target_x,self.target_y)) >= 2 and self.success:
            stepx,stepy=libtcod.path_walk(self.path,False)
            moved=monster.move(stepx-monster.x,stepy-monster.y)

        if not moved:
            if stepx!=0 and stepy!=0:
                blocking=get_object(stepx,stepy)
                if blocking is not None and hasattr(blocking,"fighter") and blocking.fighter is not None:
                    self.recalculate()
                    if blocking.fighter.hp > 0 and monster.distance_to(blocking) < 2:
                        monster.fighter.attack(blocking)
                else:
                    self.randomize_target()
            else:
                self.randomize_target()

class Item:
    #an item that can be picked up and used.
    def __init__(self, use_function=None,use_arguments=None):
        self.use_function = use_function
        self.use_arguments = use_arguments
    def pick_up(self):
        #add to the player's inventory and remove from the map
        if len(inventory) >= 26:
            message(self.owner.name + 'ei mahdu reppuusi.', libtcod.yellow)
        else:
            inventory.append(self.owner)
            objects.remove(self.owner)
            playsound('assets/sounds/pickup.wav')
            message('Otat ' + self.owner.name + 'n maasta.', libtcod.sepia)
    def use(self):
        if self.owner.equipment:
            self.owner.equipment.toggle_equip()
            return
        #just call the "use_function" if it is defined
        if self.use_function is None:
            message(self.owner.name + 'a ei voi kuluttaa.', libtcod.sepia)
        else:
            if self.use_function(player,self,self.use_arguments) != 'cancelled':
                inventory.remove(self.owner)  #destroy after use, unless it was cancelled for some reason
    def drop(self):
        #add to the map and remove from the player's inventory. also, place it at the player's coordinates
        objects.append(self.owner)
        inventory.remove(self.owner)
        self.owner.x = player.x
        self.owner.y = player.y
        #special case: if the object has the Equipment component, dequip it before dropping
        if self.owner.equipment:
            self.owner.equipment.dequip()
        message('Tiputit ' + self.owner.name + 'n.', libtcod.yellow)

class Equipment:
    #an object that can be equipped, yielding bonuses. automatically adds the Item component.
    def __init__(self, slot, power_bonus=0, defense_bonus=0, max_hp_bonus=0):
        self.power_bonus = power_bonus
        self.defense_bonus = defense_bonus
        self.max_hp_bonus = max_hp_bonus
        self.slot = slot
        self.is_equipped = False

    def toggle_equip(self):  #toggle equip/dequip status
        if self.is_equipped:
            self.dequip()
        else:
            self.equip()

    def equip(self):
        #equip object and show a message about it
        #if the slot is already being used, dequip whatever is there first
        old_equipment = get_equipped_in_slot(self.slot)
        if old_equipment is not None:
            old_equipment.dequip()
        self.is_equipped = True
        message(self.slot + 'si puristaa nyt ' + self.owner.name + 'a', libtcod.yellow)

    def dequip(self):
        #dequip object and show a message about it
        if not self.is_equipped: return
        self.is_equipped = False
        message('Laitat ' + self.owner.name + 'n takaisin reppuusi.', libtcod.yellow)

def get_equipped_in_slot(slot):  #returns the equipment in a slot, or None if it's empty
    for obj in inventory:
        if obj.equipment and obj.equipment.slot == slot and obj.equipment.is_equipped:
            return obj.equipment
    return None

def get_all_equipped(obj):  #returns a list of equipped items
    if obj == player:
        equipped_list = []
        for item in inventory:
            if item.equipment and item.equipment.is_equipped:
                equipped_list.append(item.equipment)
        return equipped_list
    else:
        return []  #other objects have no equipment

def player_death(player):
    #the game ended!
    global game_state
    message('KUKISTUIT!',libtcod.red)
    game_state = 'dead'

    #for added effect, transform the player into a corpse!
    player.char = '%'
    player.color = libtcod.dark_red

def monster_death(monster):
    #transform it into a nasty corpse! it doesn't block, can't be
    #attacked and doesn't move
    message(monster.name.capitalize() + ' kukistui!',libtcod.green,monster.x,monster.y)
    monster.char = '%'
    monster.color = libtcod.dark_red
    monster.blocks = False
    monster.fighter = None
    monster.ai = None
    monster.name = monster.name + "n ruumis"
    monster.send_to_back()


def spell_heal(caster,parent,arguments=[10]):
    #heal the player
    if caster.fighter.hp == caster.fighter.max_hp:
        message('Olet jo elinvoimainen.', libtcod.sepia)
        return 'cancelled'
    message('Haavasi alkavat tuntua paremmilta!', libtcod.green)
    caster.fighter.heal(arguments[0])

def spell_eat(caster,parent,arguments=[10]):
    if caster.fighter.hunger == caster.fighter.base_max_hunger:
        message('Vatsasi on jo pullollaan.', libtcod.sepia)
        return 'cancelled'
    message('Ahdat '+parent.owner.name+'a naamaasi, namskis maiskis lurpsis!', libtcod.green)
    caster.fighter.feed(arguments[0])

def spell_explode(caster,parent,arguments):
    message('KAPYYM!!!!!!! '+parent.owner.name+' posahti!', libtcod.red)
    caster.fighter.take_damage(60-(caster.fighter.defense*2))

def arkku_interact(object):
    message("Avaat arkun",libtcod.green)
    loot=[]
    possible=["Taikajuoma","Miekka", "Kilpi","Kakku", "Mokkapala", "Impostor_kakku"]
    morkoarkku=False
    if libtcod.random_get_int(0,1,30)==1:
        morkoarkku=True
    for ox in range(-1,2):
        for oy in range(-1,2):
            if morkoarkku and is_blocked(object.x+ox,object.y+oy)==None:
                thing=new_object("Morko")
                thing.x=object.x+ox
                thing.y=object.y+oy
                objects.append(thing)
            elif libtcod.random_get_int(0,1,6)==1 and is_blocked(object.x+ox,object.y+oy)==None:
                choice=random.choice(possible)
                thing=new_object(choice)
                thing.x=object.x+ox
                thing.y=object.y+oy
                objects.append(thing)
                loot.append(thing.name)
    objects.remove(object)
    objects.append(Object(object.x, object.y, "=", "Tyhjä arkku", libtcod.gray, blocks=False))
    if morkoarkku:
        message("Arkusta hyppää esiin mörköarmeija!",libtcod.red)
    elif len(loot)>0:
        message("Arkusta löytyy "+", ".join(loot))
    else:
        message("Arkku on tyhjä!")

#defines objects/monsters
def new_object(what):
    objects_list={
        "Sompi": Object(0, 0, "S", "Sompi", libtcod.light_green,blocks=True, fighter=Fighter(hp=7, hunger=1000, defense=0, power=10, xp=40, death_function=monster_death), ai=NoobMonster()),
        "Morko": Object(0, 0, "M", "Morko", libtcod.green,blocks=True, fighter=Fighter(hp=12, hunger=1000, defense=0, power=5, xp=80, death_function=monster_death), ai=BasicMonster()),
        "Kyrssi": Object(0, 0, "K", "Kyrssi", libtcod.green,blocks=True, fighter=Fighter(hp=30, hunger=1000, defense=10, power=10, xp=200, death_function=monster_death), ai=BasicMonster(2)),
        "Kaareni": Object(0, 0, "C", "Kaareni", libtcod.gray,blocks=True, fighter=Fighter(hp=20, hunger=1000, defense=0, power=20, xp=60, death_function=monster_death), ai=Wandering()),
        "Tomuttaja": Object(0, 0, "T", "Tomuttaja", libtcod.red,blocks=True, fighter=Fighter(hp=10, hunger=1000, defense=5, power=10, xp=100, death_function=monster_death), ai=AdvancedMonster()),

        "Taikajuoma": Object(0, 0, "!", "Taikajuoma", libtcod.purple,blocks=False, item = Item(use_function=spell_heal,use_arguments=[10])),
        "Puukko": Object(0, 0, "/", "Puukko", libtcod.gray, blocks=False, equipment=Equipment("oikea nyrkki", power_bonus=2)),
        "Miekka": Object(0, 0, "/", "Miekka", libtcod.gray, blocks=False, equipment=Equipment("oikea nyrkki", power_bonus=5)),
        "Sauva": Object(0, 0, "/", "Sauva", libtcod.white, blocks=False, equipment=Equipment("oikea nyrkki", power_bonus=15)),
        "Kilpi": Object(0, 0, "[", "Kilpi", libtcod.white, blocks=False, equipment=Equipment("vasen nyrkki", defense_bonus=5)),
        "Kakku": Object(0, 0, "%", "Kakku", libtcod.white, blocks=False, item=Item(use_function=spell_eat,use_arguments=[20])),
        "Mokkapala": Object(0, 0, "%", "Mokkapala", libtcod.Color(210,105,30), blocks=False, item = Item(use_function=spell_eat,use_arguments=[15])),
        "Impostor_kakku": Object(0, 0, "%", "Kakku", libtcod.gray, blocks=False, item=Item(use_function=spell_explode)),
        "Arkku": Object(0, 0, "=", "Arkku", libtcod.yellow, blocks=False, actions={"interact":arkku_interact}),
    }
    return objects_list[what]
#defines objects/monsters spawnrate
spawn={
    1: {"monsters":2,"monster":{"Sompi":99,"Morko":1},"items":1,"item":{"Arkku":90,"Kakku":10, "Mokkapala":10},"-rooms":1,"+rooms":6},
    4: {"monsters":4,"monster":{"Sompi":59,"Morko":11,"Kaareni":30},"items":3,"item":{"Puukko":30,"Taikajuoma":60,"Arkku":10, "Kakku":5,"Mokkapala":5},"-rooms":3,"+rooms":6},
    7: {"monsters":4,"monster":{"Morko":90,"Sompi":9,"Tomuttaja":1},"items":3,"item":{"Puukko":10, "Taikajuoma":50,"Miekka":20,"Kakku":10, "Mokkapala":10, "Impostor_kakku":10,"Sauva": 5},"-rooms":1, "+rooms":8},
    11: {"monsters":3,"monster":{"Morko":60,"Kyrssi":18,"Tomuttaja":2,"Kaareni":20},"items":1,"item":{"Kilpi":1,"Taikajuoma":68,"Miekka":1,"Impostor_kakku":5,"Kakku":10, "Mokkapala":10, "Arkku":15,"Sauva":5},"-rooms":5, "+rooms":12},
}

def from_dungeon_level(table):
    #returns a value that depends on level. the table specifies what value occurs after each level, default is 0.
    for (value, level) in reversed(table):
        if dungeon_level >= level:
            return value
    return 0

def player_move_or_attack(dx, dy):
    global fov_recompute

    #the coordinates the player is moving to/attacking
    x = player.x + dx
    y = player.y + dy

    #try to find an attackable object there
    target = None
    for object in objects:
        if object.fighter and object.x == x and object.y == y:
            target = object
            break

    #attack if target found, move otherwise
    r=True
    if target is not None:
        player.fighter.attack(target)
    else:
        r=player.move(dx, dy)
        fov_recompute = True

    items=get_names(player.x,player.y)
    if items!=None:
        message('Maassa on '+items, libtcod.sepia)
    return r

def get_names(x,y):
    #create a list with the names of all objects at the mouse's coordinates and in FOV
    names = [obj.name for obj in objects
        if obj.x == x and obj.y == y and not(obj.player) and libtcod.map_is_in_fov(fov_map, obj.x, obj.y)]

    namestr = ', '.join(names)  #join the names, separated by commas
    if len(names)>0:
        return namestr.capitalize()
    else:
         return None

def is_blocked(x, y):
    if x<1 or x>MAP_WIDTH-1 or y<1 or y>MAP_HEIGHT-1:
        return True
    #first test the map tile
    if map[x][y].blocked:
        return True

    #now check for any blocking objects
    for object in objects:
        if object.blocks and object.x == x and object.y == y:
            return object

    return None

def get_object(x, y):
    for object in objects:
        if object.x == x and object.y == y:
            return object
    return None


def create_room(room):
    global map
    #go through the tiles in the rectangle and make them passable
    for x in range(room.x1, room.x2+1):
        for y in range(room.y1, room.y2+1):
            if x==room.x1 or x==room.x2 or y==room.y1 or y==room.y2:
                if map[x][y].blocked:
                    map[x][y]=Tile(True, char="#",color=libtcod.gray,bgcolor=color_light_wall)
            else:
                map[x][y]=Tile(False, char=".",color=libtcod.gray,bgcolor=color_light_ground)

def randomwalk(tiles):
    count=0
    where=random.choice(rooms).center()
    x=random.randint(3,MAP_WIDTH-3)
    y=random.randint(3,MAP_HEIGHT-3)
    while count<tiles:
        if map[x][y].blocked or random.randint(0,4)==4:
            count+=1
            map[x][y]=Tile(False, char="'",color=libtcod.gray,bgcolor=color_light_ground)
        sx=0
        sy=0
        while (x+sx<2 or x+sx>MAP_WIDTH-2 or y+sy<2 or y+sy>MAP_HEIGHT-2 or (sx==0 and sy==0)):
            sx=random.randint(-1,1)
            sy=random.randint(-1,1)
        x,y=x+sx,y+sy

def random_choice_index(chances):  #choose one option from list of chances, returning its index
    #the dice will land on some number between 1 and the sum of the chances
    dice = libtcod.random_get_int(0, 1, sum(chances))

    #go through all chances, keeping the sum so far
    running_sum = 0
    choice = 0
    for w in chances:
        running_sum += w

        #see if the dice landed in the part that corresponds to this choice
        if dice <= running_sum:
            return choice
        choice += 1
    return choice

def random_choice(chances_dict):
    #choose one option from dictionary of chances, returning its key
    chances = chances_dict.values()
    strings = list(chances_dict.keys())
    return strings[random_choice_index(chances)]

def place_objects(room):
    error=True
    level=dungeon_level
    while error:
        try:
            max_monsters = spawn[level]["monsters"]
            monster_chances = spawn[level]["monster"]
            max_items = spawn[level]["items"]
            item_chances = spawn[level]["item"]
            error=False
        except KeyError:
            level-=1

    #choose random number of monsters
    num_monsters = libtcod.random_get_int(0, 0, max_monsters)

    for i in range(num_monsters):
        #choose random spot for this monster
        x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
        y = libtcod.random_get_int(0, room.y1+1, room.y2-1)
        if is_blocked(x, y)==None:
            choice=random_choice(monster_chances)
            monster=new_object(choice)
            monster.x=x
            monster.y=y
            objects.append(monster)
    #choose random number of items
    num_items = libtcod.random_get_int(0, 0, max_items)
    for i in range(num_items):
        #choose random spot for this item
        x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
        y = libtcod.random_get_int(0, room.y1+1, room.y2-1)
        #only place it if the tile is not blocked
        if is_blocked(x, y)==None:
            choice=random_choice(item_chances)
            item=new_object(choice)
            item.x=x
            item.y=y
            objects.append(item)

def create_h_tunnel(x1, x2, y):
    global map
    #horizontal tunnel. min() and max() are used in case x1>x2
    for x in range(min(x1, x2), max(x1, x2) + 1):
        map[x][y]=Tile(False, char=".",color=libtcod.gray,bgcolor=color_light_ground)


def create_v_tunnel(y1, y2, x):
    global map
    #vertical tunnel
    for y in range(min(y1, y2), max(y1, y2) + 1):
        map[x][y]=Tile(False, char=".",color=libtcod.gray,bgcolor=color_light_ground)


def next_level():
    global dungeon_level
    #advance to the next level
    if player.fighter.hunger > 0:
        message('Otat hetken lepotauon.', libtcod.green)
        player.fighter.heal(player.fighter.max_hp / 2)  #heal the player by 50%
        message('Harvinaisen rauhanhetken kuluttua jatkat kohti tyrmien uumenia.', libtcod.sepia)
        dungeon_level += 1
        make_map()  #create a fresh new level!
        initialize_fov()
    else:
        message('Jatkat nälkäisenä kohti tyrmien uumenia.', libtcod.sepia)
        dungeon_level += 1
        make_map()  #create a fresh new level!
        initialize_fov()

def make_map():
    global map, objects, stairs, path_map, rooms

    #the list of objects with just the player
    objects = [player]
    (prev_x, prev_y) = (0, 0)

    #fill map with "blocked" tiles
    map = [[Tile(True, char="+",color=libtcod.gray,bgcolor=color_light_wall)
        for y in range(MAP_HEIGHT) ]
            for x in range(MAP_WIDTH) ]

    rooms = []
    num_rooms = 0
    level=dungeon_level
    error=True
    while error:
        try:
            min_rooms = spawn[level]["-rooms"]
            max_rooms = spawn[level]["+rooms"]
            error=False
        except KeyError:
            level-=1

    for r in range(libtcod.random_get_int(0,min_rooms,max_rooms)):
        #random width and height
        w = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        h = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        #random position without going out of the boundaries of the map
        x = clamp(prev_x-ROOM_MAX_SIZE+5, libtcod.random_get_int(0, 0, MAP_WIDTH - w - 1), prev_x+ROOM_MAX_SIZE+5 )
        y = clamp(prev_y-ROOM_MAX_SIZE+5, libtcod.random_get_int(0, 0, MAP_HEIGHT - h - 1), prev_y+ROOM_MAX_SIZE+5 )

        #"Rect" class makes rectangles easier to work with
        new_room = Rect(x, y, w, h)

        #run through the other rooms and see if they intersect with this one
        failed = False
        for other_room in rooms:
            if new_room.intersect(other_room):
                failed = True
                break

        if not failed:
            #this means there are no intersections, so this room is valid

            #"paint" it to the map's tiles
            create_room(new_room)

            #center coordinates of new room, will be useful later
            (new_x, new_y) = new_room.center()

            if num_rooms == 0:
                #this is the first room, where the player starts at
                player.x = new_x
                player.y = new_y
            else:
                #all rooms after the first:
                #connect it to the previous room with a tunnel

                #center coordinates of previous room
                (prev_x, prev_y) = rooms[num_rooms-1].center()

                #draw a coin (random number that is either 0 or 1)
                if libtcod.random_get_int(0, 0, 1) == 1:
                    #first move horizontally, then vertically
                    create_h_tunnel(prev_x, new_x, prev_y)
                    create_v_tunnel(prev_y, new_y, new_x)
                else:
                    #first move vertically, then horizontally
                    create_v_tunnel(prev_y, new_y, prev_x)
                    create_h_tunnel(prev_x, new_x, new_y)

            #finally, append the new room to the list
            place_objects(new_room)
            rooms.append(new_room)
            num_rooms += 1
    if random.randint(0,10)<1:
        randomwalk(random.randint(50,500))
    #create stairs at the center of the last room
    stairs = Object(new_x, new_y, '<', 'portaat', libtcod.white)
    objects.append(stairs)
    stairs.send_to_back()  #so it's drawn below the monsters
    path_map = libtcod.map_new(MAP_WIDTH, MAP_HEIGHT)
    for y in range(MAP_HEIGHT):
        for x in range(MAP_WIDTH):
            if map[x][y].blocked:
                libtcod.map_set_properties(path_map, x, y, True, False)
            else:
                libtcod.map_set_properties(path_map, x, y, True, True)

def menu(header, options, width):
    if len(options) > 26: raise ValueError('Cannot have a menu with more than 26 options.')
    #calculate total height for the header (after auto-wrap) and one line per option
    header_height = libtcod.console_get_height_rect(con, 0, 0, width, SCREEN_HEIGHT, header)
    height = len(options) + header_height
    #create an off-screen console that represents the menu's window
    window = libtcod.console_new(width, height)

    #print the header, with auto-wrap
    libtcod.console_set_default_foreground(window, libtcod.white)
    libtcod.console_print_rect_ex(window, 0, 0, width, height, libtcod.BKGND_NONE, libtcod.LEFT, header)
    #print all the options
    y = header_height
    letter_index = ord('a')
    for option_text in options:
        text = '(' + chr(letter_index) + ') ' + option_text
        libtcod.console_print_ex(window, 0, y, libtcod.BKGND_NONE, libtcod.LEFT, text)
        y += 1
        letter_index += 1
    #blit the contents of "window" to the root console
    x = int(SCREEN_WIDTH/2 - width/2)
    y = int(SCREEN_HEIGHT/2 - height/2)
    libtcod.console_blit(window, 0, 0, width, height, 0, x, y, 1.0, 0.7)
    #present the root console to the player and wait for a key-press
    libtcod.console_flush()
    key = libtcod.console_wait_for_keypress(True)
    #convert the ASCII code to an index; if it corresponds to an option, return it
    index = key.c - ord('a')
    if index >= 0 and index < len(options): return index
    return None

def inventory_menu(header):
    #show a menu with each item of the inventory as an option
    if len(inventory) == 0:
        options = ['Reppusi on tyhjä.']
    else:
        options = []
        for item in inventory:
            text = item.name
            #show additional information, in case it's equipped
            if item.equipment and item.equipment.is_equipped:
                text = text + ' ( ' + item.equipment.slot + ')'
            options.append(text)

    index = menu(header, options, INVENTORY_WIDTH)
    #if an item was chosen, return it
    if index is None or len(inventory) == 0: return None
    return inventory[index].item

def textinput(header, width):
    #calculate total height for the header (after auto-wrap) and one line per option
    header_height = libtcod.console_get_height_rect(con, 0, 0, width, SCREEN_HEIGHT, header)
    height = header_height+2
    #create an off-screen console that represents the menu's window
    window = libtcod.console_new(width, height)

    #print the header, with auto-wrap
    libtcod.console_set_default_foreground(window, libtcod.white)
    libtcod.console_print_rect_ex(window, 0, 0, width, height, libtcod.BKGND_NONE, libtcod.LEFT, header)
    text=''
    key=None
    while key==None or key.vk != libtcod.KEY_ENTER:
        libtcod.console_clear(con)
        libtcod.console_print_rect_ex(window, 0, 2, width, height, libtcod.BKGND_NONE, libtcod.LEFT, text)
        #blit the contents of "window" to the root console
        x = int(SCREEN_WIDTH/2 - width/2)
        y = int(SCREEN_HEIGHT/2 - height/2)
        libtcod.console_blit(window, 0, 0, width, height, 0, x, y, 1.0, 1.0)
        #present the root console to the player and wait for a key-press
        libtcod.console_flush()
        key = libtcod.console_wait_for_keypress(True)
        text=text+chr(key.c)
    return text.strip()

def render_all():
    global fov_map, color_dark_wall, color_light_wall
    global color_dark_ground, color_light_ground
    global fov_recompute

    if fov_recompute:
        #recompute FOV if needed (the player moved or something)
        fov_recompute = False
        libtcod.map_compute_fov(fov_map, player.x, player.y, TORCH_RADIUS, FOV_LIGHT_WALLS, FOV_ALGO)

        #go through all tiles, and set their background color according to the FOV
        for y in range(MAP_HEIGHT):
            for x in range(MAP_WIDTH):
                cell = map[x][y]
                visible = libtcod.map_is_in_fov(fov_map, x, y)
                wall = map[x][y].block_sight
                if not visible:
                    #if it's not visible right now, the player can only see it if it's explored
                    if map[x][y].explored:
                        if wall:
                            libtcod.console_put_char_ex(con, x, y, ' ', libtcod.gray, color_dark_wall)
                        else:
                            libtcod.console_put_char_ex(con, x, y, ' ', libtcod.gray, color_dark_ground)
                else:
                    #it's visible
                    libtcod.console_put_char_ex(con, x, y, cell.char, cell.color, cell.bgcolor)
                    #since it's visible, explore it
                    map[x][y].explored = True

    #draw all objects in the list
    for object in objects:
        if object != player:
            object.draw()
    player.draw()

        #prepare to render the GUI panel
    libtcod.console_set_default_background(panel, libtcod.black)
    libtcod.console_clear(panel)

    #show the player's stats
    render_bar(1, 1, BAR_WIDTH, 'HP', player.fighter.hp, player.fighter.max_hp,
        libtcod.green, libtcod.darker_red)
    libtcod.console_set_default_foreground(panel, libtcod.white)
    render_bar(1, 2, BAR_WIDTH, 'HUNGER', player.fighter.hunger, player.fighter.base_max_hunger,
        libtcod.Color(210,105,30), libtcod.darker_red)
    libtcod.console_set_default_foreground(panel, libtcod.white)
    libtcod.console_print_ex(panel, 1, 5, libtcod.BKGND_NONE, libtcod.LEFT, 'Tyrmien syvyys ' + str(dungeon_level))
    libtcod.console_set_default_foreground(panel, libtcod.yellow)
    libtcod.console_print_ex(panel, 1, 3, libtcod.BKGND_NONE, libtcod.LEFT, 'Voima/Suoja: ' + str(player.fighter.power) + '/' + str(player.fighter.defense))
    libtcod.console_print_ex(panel, 1, 4, libtcod.BKGND_NONE, libtcod.LEFT, 'Kokemus: ' + str(player.level))

    #print the game messages, one line at a time
    y = 1
    for (line, color) in game_msgs:
        libtcod.console_set_default_foreground(panel, color)
        libtcod.console_print_ex(panel, MSG_X, y, libtcod.BKGND_NONE, libtcod.LEFT, line)
        y += 1
    #blit the contents of "con" to the root console
    libtcod.console_blit(con, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, 0, 0, 0)
    #blit the contents of "panel" to the root console
    libtcod.console_blit(panel, 0, 0, SCREEN_WIDTH, PANEL_HEIGHT, 0, 0, PANEL_Y)
    for object in objects:
        object.clear()

def render_bar(x, y, total_width, name, value, maximum, bar_color, back_color):
    #render the background first
    libtcod.console_set_default_background(panel, back_color)
    libtcod.console_rect(panel, x, y, total_width, 1, False, libtcod.BKGND_SCREEN)

    #render a bar (HP, experience, etc). first calculate the width of the bar
    bar_width = int(float(value) / maximum * total_width)

    #now render the bar on top
    libtcod.console_set_default_background(panel, bar_color)
    if bar_width > 0:
        libtcod.console_rect(panel, x, y, bar_width, 1, False, libtcod.BKGND_SCREEN)
    #finally, some centered text with the values
    libtcod.console_set_default_foreground(panel, libtcod.black)
    libtcod.console_print_ex(panel, x + int(total_width/2), y, libtcod.BKGND_NONE, libtcod.CENTER,
        name + ': ' + str(value) + '/' + str(maximum))

def handle_keys():
    global fov_recompute

    #key = libtcod.console_check_for_keypress()  #real-time
    key = libtcod.console_wait_for_keypress(True)  #turn-based
    key_char = chr(key.c)

    if key.vk == libtcod.KEY_F11:
        #Alt+Enter: toggle fullscreen
        libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())

    elif key.vk == libtcod.KEY_ESCAPE:
        return 'exit'
    r=True
    #movement keys
    if game_state == 'playing':
        if key_char == 'w' or key.vk == libtcod.KEY_KP8:
            r=player_move_or_attack(0, -1)

        elif key_char == 's' or key.vk == libtcod.KEY_KP2:
            r=player_move_or_attack(0, 1)

        elif key_char == 'a' or key.vk == libtcod.KEY_KP4:
            r=player_move_or_attack(-1, 0)

        elif key_char == 'd' or key.vk == libtcod.KEY_KP6:
            r=player_move_or_attack(1, 0)

        elif key_char == 'q' or key.vk == libtcod.KEY_KP7:
            r=player_move_or_attack(-1, -1)

        elif key_char == 'e' or key.vk == libtcod.KEY_KP9:
            r=player_move_or_attack(1, -1)

        elif key_char == 'z' or key.vk == libtcod.KEY_KP1:
            r=player_move_or_attack(-1, 1)

        elif key_char == 'c' or key.vk == libtcod.KEY_KP3:
            r=player_move_or_attack(1, 1)
        else:
            #test for other keys
            if key_char == 'o':
                #pick up an item
                upped=False
                for object in objects:  #look for an item in the player's tile
                    if object.x == player.x and object.y == player.y:
                        if object.item:
                            object.item.pick_up()
                            upped=True
                            break
                        if "interact" in object.actions:
                            object.actions["interact"](object)
                            upped=True
                            break
                if not upped:
                    message('Maassa ei ole otettavaa.',libtcod.dark_red)
                    return 'didnt-take-turn'
            elif key_char == 'r':
                #show the inventory; if an item is selected, use it
                chosen_item = inventory_menu('Paina esineen nappia kuluttaaksesi esineen, tai jotakin muuta peruuttaaksesi.\n')
                if chosen_item is not None:
                    chosen_item.use()
                else:
                    return 'didnt-take-turn'
            elif key_char == 't':
                #show the inventory; if an item is selected, drop it
                chosen_item = inventory_menu('Paina esineen nappia tiputtaaksesi esineen, tai jotakin muuta peruuttaaksesi.\n')
                if chosen_item is not None:
                    chosen_item.drop()
                else:
                    return 'didnt-take-turn'
            elif key_char == 'p':
                #go down stairs, if the player is on them
                if stairs.x == player.x and stairs.y == player.y:
                    next_level()
                else:
                    message('Maassa ei ole portaita joita kulkea alas.',libtcod.dark_red)
                    return 'didnt-take-turn'
            else:
                message('Nappia ei tunnistettu',libtcod.dark_red)
                return 'didnt-take-turn'
        if not r:
            message('Osut muuriin.',libtcod.dark_red)
            return 'didnt-take-turn'

def message(new_msg, color = libtcod.white,x=None,y=None):
    #split the message if necessary, among multiple lines
    if x==None or libtcod.map_is_in_fov(fov_map, x, y):
        new_msg_lines = textwrap.wrap(new_msg, MSG_WIDTH)

        for line in new_msg_lines:
            #if the buffer is full, remove the first line to make room for the new one
            if len(game_msgs) == MSG_HEIGHT:
                del game_msgs[0]

            #add the new line as a tuple, with the text and the color
            game_msgs.append( (line, color) )
            y = 1
            libtcod.console_set_default_background(panel, libtcod.black)
            libtcod.console_clear(panel)
            render_all()
            for (line, color) in game_msgs:
                libtcod.console_set_default_foreground(panel, color)
                libtcod.console_print_ex(panel, MSG_X, y, libtcod.BKGND_NONE, libtcod.LEFT, line)
                y += 1
            libtcod.console_blit(panel, 0, 0, SCREEN_WIDTH, PANEL_HEIGHT, 0, 0, PANEL_Y)
            libtcod.console_flush()

def msgbox(text, width=50):
    menu(text, [], width)  #use menu() as a sort of "message box"

#############################################
# Initialization & Main Loop
#############################################

libtcod.console_set_custom_font('assets/terminator10x16.png', libtcod.FONT_TYPE_GREYSCALE | libtcod.FONT_LAYOUT_CP437)
libtcod.console_init_root(SCREEN_WIDTH, SCREEN_HEIGHT, 'TYRMÄ', False)
libtcod.sys_set_fps(LIMIT_FPS)
con = libtcod.console_new(SCREEN_WIDTH, SCREEN_HEIGHT)
panel = libtcod.console_new(SCREEN_WIDTH, PANEL_HEIGHT)


game_state = 'playing'

def play_game():
    global key, mouse

    player_action = None

    mouse = libtcod.Mouse()
    key = libtcod.Key()
    while not libtcod.console_is_window_closed():
        #render the screen
        libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE,key,mouse)
        render_all()

        libtcod.console_flush()
        check_level_up()

        #erase all objects at their old locations, before they move
        for object in objects:
            object.clear()

        #handle keys and exit game if needed
        player_action = handle_keys()
        if player_action == 'exit':
            save_game()
            break

        #let monsters take their turn
        if game_state == 'playing' and player_action != 'didnt-take-turn':
            for object in objects:
                if object.ai:
                    object.ai.take_turn()

def main_menu():
    img = libtcod.image_load('assets/menu.png')

    while not libtcod.console_is_window_closed():
        #show the background image, at twice the regular console resolution
        libtcod.image_blit_2x(img, 0, 0, 0)
        #show the game's title, and some credits!
        libtcod.console_set_default_foreground(0, libtcod.light_yellow)
        libtcod.console_print_ex(0, int(SCREEN_WIDTH/2), int(SCREEN_HEIGHT/2-4), libtcod.BKGND_NONE, libtcod.CENTER,
            'TYRMÄ')
        libtcod.console_print_ex(0, int(SCREEN_WIDTH/2), int(SCREEN_HEIGHT-2), libtcod.BKGND_NONE, libtcod.CENTER,
            'By Hakaponttoauto')
        #show options and wait for the player's choice
        choice = menu('', ['Uusi peli', 'Jatka tallennuksesta', 'Lopeta'], 24)

        if choice == 0:  #new game
            new_game()
            play_game()
        elif choice == 1:  #load last game
            try:
                load_game()
            except:
                msgbox('\n Ei tallennettua peliä.\n', 24)
                continue
            play_game()
        elif choice == 2:  #quit
            break
main_menu()
