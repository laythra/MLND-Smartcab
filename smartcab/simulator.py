
"""
Simulator which creates an environment, agents, and updates all by discrete time steps.
"""

# Suppress matplotlib user warnings
# Necessary for newer version of matplotlib
import warnings
warnings.filterwarnings("ignore", category = UserWarning, module = "matplotlib")

import os
import time
import random
import importlib
import csv

import colory



class Simulator(object):
    """
    Simulate agents in a dynamic smartcab environment.
    Uses PyGame to display GUI, if available.
    """

    colors = {
        'black'   : (  0,   0,   0),
        'white'   : (255, 255, 255),
        'red'     : (255,   0,   0),
        'green'   : (  0, 255,   0),
        'dgreen'  : (  0, 228,   0),
        'blue'    : (  0,   0, 255),
        'cyan'    : (  0, 200, 200),
        'magenta' : (200,   0, 200),
        'yellow'  : (255, 255,   0),
        'mustard' : (200, 200,   0),
        'orange'  : (255, 128,   0),
        'maroon'  : (200,   0,   0),
        'crimson' : (128,   0,   0),
        'gray'    : (155, 155, 155)
    }


    def __init__(self, env, size=None, update_delay=2.0, display=True, log_metrics=False, optimized=False):
        """
        Initialize the simulation.
        """
        self.env = env
        #?
        self.size = size if size is not None else \
                    ((self.env.grid_size[0] + 1) * self.env.block_size,
                     (self.env.grid_size[1] + 2) * self.env.block_size)
        self.width, self.height = self.size
        self.road_width = 44 #. magic number

        self.bg_color = self.colors['gray']
        self.road_color = self.colors['black']
        self.line_color = self.colors['mustard']
        self.boundary = self.colors['black']
        self.stop_color = self.colors['crimson']

        self.quit = False
        self.start_time = None
        self.current_time = 0.0
        self.last_updated = 0.0
        self.update_delay = update_delay  # duration between each step (in seconds)

        self.display = display
        if self.display:
            try:
                self.pygame = importlib.import_module('pygame')
                self.pygame.init()
                self.screen = self.pygame.display.set_mode(self.size)
                self._logo = self.pygame.transform.smoothscale(self.pygame.image.load(os.path.join("images", "logo.png")), (self.road_width, self.road_width))

                self._ew = self.pygame.transform.smoothscale(self.pygame.image.load(os.path.join("images", "east-west.png")), (self.road_width, self.road_width))
                self._ns = self.pygame.transform.smoothscale(self.pygame.image.load(os.path.join("images", "north-south.png")), (self.road_width, self.road_width))

                self.frame_delay = max(1, int(self.update_delay * 1000))  # delay between GUI frames in ms (min: 1)
                self.agent_sprite_size = (32, 32)
                self.primary_agent_sprite_size = (42, 42)
                self.agent_circle_radius = 20  # radius of circle, when using simple representation
                for agent in self.env.agent_states:
                    if agent.color == 'white':
                        agent._sprite = self.pygame.transform.smoothscale(self.pygame.image.load(os.path.join("images", "car-{}.png".format(agent.color))), self.primary_agent_sprite_size)
                    else:
                        agent._sprite = self.pygame.transform.smoothscale(self.pygame.image.load(os.path.join("images", "car-{}.png".format(agent.color))), self.agent_sprite_size)
                    agent._sprite_size = (agent._sprite.get_width(), agent._sprite.get_height())

                self.font = self.pygame.font.Font(None, 20)
                self.paused = False
            except ImportError as e:
                self.display = False
                print "Simulator.__init__(): Unable to import pygame; display disabled.\n{}: {}".format(e.__class__.__name__, e)
            except Exception as e:
                self.display = False
                print "Simulator.__init__(): Error initializing GUI objects; display disabled.\n{}: {}".format(e.__class__.__name__, e)

        # Setup metrics to report
        self.log_metrics = log_metrics
        self.optimized = optimized

        if self.log_metrics:
            #. a->agent
            a = self.env.primary_agent

            # Set log files
            if a.learning:
                if self.optimized: # Whether the user is optimizing the parameters and decay functions
                    self.log_filename = os.path.join("logs", "sim_improved-learning.csv")
                    self.table_filename = os.path.join("logs","sim_improved-learning.txt")
                else:
                    self.log_filename = os.path.join("logs", "sim_default-learning.csv")
                    self.table_filename = os.path.join("logs","sim_default-learning.txt")

                self.table_file = open(self.table_filename, 'wb')
            else:
                self.log_filename = os.path.join("logs", "sim_no-learning.csv")

            #. this should be expanded so the csv is more human (and excel) readable
            self.log_fields = ['trial', 'testing', 'parameters', 'initial_deadline', 'final_deadline', 'net_reward', 'actions', 'success']
            self.log_file = open(self.log_filename, 'wb')
            self.log_writer = csv.DictWriter(self.log_file, fieldnames=self.log_fields)
            self.log_writer.writeheader()


    def run(self, tolerance=0.05, n_test=0):
        """
        Run a simulation of the environment.

        tolerance - the minimum epsilon necessary to switch from training to testing (if enabled)
        n_test    - the number of testing trials to run
        """

        self.quit = False

        # n_trials_min = 20 # fixed
        n_trials_min = 2 #. pass this in?

        # Get the primary agent
        #. a->agent
        a = self.env.primary_agent

        total_trials = 1
        testing = False
        trial = 1

        # Define table format and print header
        # Note that colored cells need 9 extra characters to account for ANSI codes
        #. put into fn?
        header_format = "{:9} {:5}  {:>8}  {:10}  {:10}  {:9}  {:8}  {:>8}"
        row_format =    "{:9} {:5}  {:8.2f}  {:>19}  {:>19}  {:>18}  {:8.3f}  {:>17}"
        print header_format.format("Type", "Trial", "Epsilon", "Avg Reward", "Violations",
                                   "Accidents", "Coverage", "Status")
        print "-" * 80

        while True:

            # Flip testing switch
            if not testing:
                if total_trials > n_trials_min: # Must complete minimum number of training trials
                    if a.learning:
                        if a.epsilon < tolerance: # assume epsilon decays towards 0
                            testing = True
                            trial = 1
                    else:
                        testing = True
                        trial = 1

            # Break if we've reached the limit of testing trials
            else:
                if trial > n_test:
                    break

            # Pretty print to terminal
            # print
            # print "/-------------------------"
            # if testing:
            #     print "| Testing trial {}".format(trial)
            # else:
            #     print "| Training trial {}".format(trial)
            # print "\-------------------------"
            # print

            self.env.reset(testing)
            self.current_time = 0.0
            self.last_updated = 0.0
            self.start_time = time.time()
            while True:
                try:
                    # Update current time
                    self.current_time = time.time() - self.start_time

                    # Handle GUI events
                    if self.display:
                        for event in self.pygame.event.get():
                            if event.type == self.pygame.QUIT:
                                self.quit = True
                            elif event.type == self.pygame.KEYDOWN:
                                if event.key == 27:  # Esc #. magic#
                                    self.quit = True
                                elif event.unicode == u' ': #. magic
                                    self.paused = True

                        if self.paused:
                            self.pause()

                    # Update environment
                    #. and all agents within
                    if self.current_time - self.last_updated >= self.update_delay:
                        self.env.step() #. this updates all agents, eh?
                        self.last_updated = self.current_time

                    # Render text
                    self.render_text(trial, testing)

                    # Render GUI and sleep
                    if self.display:
                        self.render(trial, testing)
                        self.pygame.time.wait(self.frame_delay)

                except KeyboardInterrupt:
                    self.quit = True
                finally:
                    if self.quit or self.env.done:
                        break

            if self.quit:
                break

            # Collect metrics from trial
            if self.log_metrics:
                self.log_writer.writerow({
                    'trial': trial,
                    'testing': self.env.trial_data['testing'],
                    'parameters': self.env.trial_data['parameters'],
                    'initial_deadline': self.env.trial_data['initial_deadline'],
                    'final_deadline': self.env.trial_data['final_deadline'],
                    'net_reward': self.env.trial_data['net_reward'],
                    'actions': self.env.trial_data['actions'],
                    'success': self.env.trial_data['success']
                })

            # Trial finished
            # if self.env.success == True:
            #     print "\nTrial Completed!"
            #     print "Agent reached the destination."
            # else:
            #     print "\nTrial Aborted!"
            #     print "Agent did not reach the destination."

            #. put table stuff into fn?

            # Define table values
            data = self.env.trial_data
            trial_type = "Testing " if testing else "Training"
            epsilon    = a.epsilon
            nsteps     = data['initial_deadline'] - data['final_deadline'] # number of time steps #. get from t?
            avg_reward = colory.redgreen(float(data['net_reward'])/nsteps, "{:.2f}")
            actions    = data['actions']
            violations = colory.redgreen(actions[1] + actions[2], "{:d}", -1)
            accidents  = colory.redgreen(actions[3] + actions[4], "{:d}", -1)
            coverage   = data['coverage']
            status     = colory.green("On time") if data['success'] else colory.red("Late")

            # Print table row
            print row_format.format(trial_type, trial, epsilon, avg_reward, violations, accidents, coverage, status)

            # Increment
            total_trials = total_trials + 1
            trial = trial + 1


        # Clean up
        if self.log_metrics:

            if a.learning:

                # f.write("/-----------------------------------------\n")
                # f.write("| State-action rewards from Q-Learning\n")
                # f.write("\-----------------------------------------\n\n")

                #. a->agent

                # Define output table format
                # Cells are all 8 chars wide with 2 chars padding
                n_state_values   = len(a.states)
                n_actions        = len(a.valid_actions)
                first_row_format = "{:^" + str(n_state_values*(8+2)) + "}" + " | " + "{:^" + str(n_actions*(8+2)) + "}"
                header_format    = "{:8}  " * n_state_values + " | " + "{:>8}  " * n_actions
                row_format       = header_format

                # Define output table header rows
                first_row        = first_row_format.format("States", "Actions and Rewards")
                separator_row    = "-" * ((n_state_values + n_actions)*(8+2)) + "-"
                header_values    = a.states + tuple(a.valid_actions) # combine state and action names
                header_row       = header_format.format(*header_values)

                # Iterate over states in the Q table and add to our output table
                #. rename a.Q to a.Q_table?
                table = []
                for state in a.Q:
                    action_rewards = a.Q[state]
                    values = []
                    for state_value in state:
                        values.append(state_value)
                    for action in a.valid_actions:
                        value = action_rewards.get(action, 0) #. 0?
                        if value:
                            value = "{:8.2f}".format(value)
                        else:
                            value = " " * 8
                        values.append(value)
                    row = row_format.format(*values)
                    table.append(row)

                # Sort the table, add the header rows, and convert to a string
                table = sorted(table)
                table = [first_row, header_row, separator_row] + table
                s = '\n'.join(table)

                # Print the table
                print
                print 'Q table:'
                print
                print s

                # Write the table to a file
                f = self.table_file
                f.write(s)
                self.table_file.close()

            self.log_file.close()

        print "\nSimulation ended..."

        # Report final metrics
        if self.display:
            self.pygame.display.quit()  # shut down pygame


    def render_text(self, trial, testing=False):
        """
        This is the non-GUI render display of the simulation.
        Simulated trial data will be rendered in the terminal/command prompt.
        """

        #. make a flag
        #. if flag then print all this stuff, with a header
        #. and in run, have it print blank line and header before each table row
        # (a bit complicated as currently outputting to a list first - fix)
        return

        status = self.env.step_data
        if status and status['waypoint'] is not None: # Continuing the trial

            # Previous State
            # if status['state']:
            #     print "Agent previous state: {}".format(status['state'])
            # else:
            #     print "!! Agent state not been updated!"

            # Result
            t = status['t']
            action = status['action']
            reward = status['reward']
            waypoint = status['waypoint']
            # ok = "SUCCESS" if reward >= 0.0 else "FAIL   "
            # ok = self.GREEN + "SUCCESS" if reward >= 0.0 else self.RED + "FAIL   "
            ok = colory.green("SUCCESS") if reward >= 0.0 else colory.red("FAIL   ")
            # ok += self.RESET
            msg = ""

            if status['violation'] == 0: # Legal
                if status['waypoint'] == status['action']: # Followed waypoint
                    msg = "Followed the waypoint {}.".format(action)
                elif status['action'] == None:
                    if status['light'] == 'red': # Stuck at red light
                        msg = "Properly idled at a red light."
                    else:
                        msg = "Idled at a green light with oncoming traffic."
                else: # Did not follow waypoint
                    msg = "Drove {} instead of {}.".format(action, waypoint)
            else: # Illegal
                if status['violation'] == 1: # Minor violation
                    msg = "Idled at a green light with no oncoming traffic."
                elif status['violation'] == 2: # Major violation
                    msg = "Attempted driving {} through a red light.".format(action)
                elif status['violation'] == 3: # Minor accident
                    msg = "Attempted driving {} through traffic and caused a minor accident.".format(action)
                elif status['violation'] == 4: # Major accident
                    msg = "Attempted driving {} through a red light with traffic and caused a major accident.".format(action)

            # Time Remaining
            if self.env.enforce_deadline:
                time = (status['deadline'] - 1) * 100.0 / (status['t'] + status['deadline'])
                # print "{:.0f}% of time remaining to reach destination.".format(time)
            else:
                print "Agent not enforced to meet deadline."

            # print "Reward {: 6.2f}: {}".format(reward, msg)
            # print "{:100} Reward {: 6.2f}".format(msg, reward)
            print "{:4} {} {: 10.2f} {}".format(t, ok, reward, msg)
            # print "\033[91mRed\033[0m"
            # print self.RED + "Red"

        # Starting new trial
        else:
            #. a->agent
            a = self.env.primary_agent
            print "Simulating trial..."
            if a.learning:
                print "epsilon = {:.4f}; alpha = {:.4f}".format(a.epsilon, a.alpha)
            else:
                print "Agent not set to learn."


    def render(self, trial, testing=False):
        """
        This is the GUI render display of the simulation.
        Supplementary trial data can be found from render_text.
        """

        # Reset the screen.
        self.screen.fill(self.bg_color)

        # Draw elements
        # * Static elements

        # Boundary
        self.pygame.draw.rect(self.screen, self.boundary, ((self.env.bounds[0] - self.env.hang)*self.env.block_size, (self.env.bounds[1]-self.env.hang)*self.env.block_size, (self.env.bounds[2] + self.env.hang/3)*self.env.block_size, (self.env.bounds[3] - 1 + self.env.hang/3)*self.env.block_size), 4)

        for road in self.env.roads:
            # Road
            self.pygame.draw.line(self.screen, self.road_color, (road[0][0] * self.env.block_size, road[0][1] * self.env.block_size), (road[1][0] * self.env.block_size, road[1][1] * self.env.block_size), self.road_width)
            # Center line
            self.pygame.draw.line(self.screen, self.line_color, (road[0][0] * self.env.block_size, road[0][1] * self.env.block_size), (road[1][0] * self.env.block_size, road[1][1] * self.env.block_size), 2)

        for intersection, traffic_light in self.env.intersections.iteritems():
            self.pygame.draw.circle(self.screen, self.road_color, (intersection[0] * self.env.block_size, intersection[1] * self.env.block_size), self.road_width/2)

            if traffic_light.state: # North-South is open
                self.screen.blit(self._ns,
                    self.pygame.rect.Rect(intersection[0]*self.env.block_size - self.road_width/2, intersection[1]*self.env.block_size - self.road_width/2, intersection[0]*self.env.block_size + self.road_width, intersection[1]*self.env.block_size + self.road_width/2))
                self.pygame.draw.line(self.screen, self.stop_color, (intersection[0] * self.env.block_size - self.road_width/2, intersection[1] * self.env.block_size - self.road_width/2), (intersection[0] * self.env.block_size - self.road_width/2, intersection[1] * self.env.block_size + self.road_width/2), 2)
                self.pygame.draw.line(self.screen, self.stop_color, (intersection[0] * self.env.block_size + self.road_width/2 + 1, intersection[1] * self.env.block_size - self.road_width/2), (intersection[0] * self.env.block_size + self.road_width/2 + 1, intersection[1] * self.env.block_size + self.road_width/2), 2)
            else:
                self.screen.blit(self._ew,
                    self.pygame.rect.Rect(intersection[0]*self.env.block_size - self.road_width/2, intersection[1]*self.env.block_size - self.road_width/2, intersection[0]*self.env.block_size + self.road_width, intersection[1]*self.env.block_size + self.road_width/2))
                self.pygame.draw.line(self.screen, self.stop_color, (intersection[0] * self.env.block_size - self.road_width/2, intersection[1] * self.env.block_size - self.road_width/2), (intersection[0] * self.env.block_size + self.road_width/2, intersection[1] * self.env.block_size - self.road_width/2), 2)
                self.pygame.draw.line(self.screen, self.stop_color, (intersection[0] * self.env.block_size + self.road_width/2, intersection[1] * self.env.block_size + self.road_width/2 + 1), (intersection[0] * self.env.block_size - self.road_width/2, intersection[1] * self.env.block_size + self.road_width/2 + 1), 2)

        # * Dynamic elements
        self.font = self.pygame.font.Font(None, 20)
        for agent, state in self.env.agent_states.iteritems():
            # Compute precise agent location here (back from the intersection some)
            agent_offset = (2 * state['heading'][0] * self.agent_circle_radius + self.agent_circle_radius * state['heading'][1] * 0.5, \
                            2 * state['heading'][1] * self.agent_circle_radius - self.agent_circle_radius * state['heading'][0] * 0.5)


            agent_pos = (state['location'][0] * self.env.block_size - agent_offset[0], state['location'][1] * self.env.block_size - agent_offset[1])
            agent_color = self.colors[agent.color]

            if hasattr(agent, '_sprite') and agent._sprite is not None:
                # Draw agent sprite (image), properly rotated
                rotated_sprite = agent._sprite if state['heading'] == (1, 0) else self.pygame.transform.rotate(agent._sprite, 180 if state['heading'][0] == -1 else state['heading'][1] * -90)
                self.screen.blit(rotated_sprite,
                    self.pygame.rect.Rect(agent_pos[0] - agent._sprite_size[0] / 2, agent_pos[1] - agent._sprite_size[1] / 2,
                        agent._sprite_size[0], agent._sprite_size[1]))
            else:
                # Draw simple agent (circle with a short line segment poking out to indicate heading)
                self.pygame.draw.circle(self.screen, agent_color, agent_pos, self.agent_circle_radius)
                self.pygame.draw.line(self.screen, agent_color, agent_pos, state['location'], self.road_width)


            if state['destination'] is not None:
                self.screen.blit(self._logo,
                    self.pygame.rect.Rect(state['destination'][0] * self.env.block_size - self.road_width/2, \
                        state['destination'][1]*self.env.block_size - self.road_width/2, \
                        state['destination'][0]*self.env.block_size + self.road_width/2, \
                        state['destination'][1]*self.env.block_size + self.road_width/2))

        # * Overlays
        self.font = self.pygame.font.Font(None, 50)
        if testing:
            self.screen.blit(self.font.render("Testing Trial %s"%(trial), True, self.colors['black'], self.bg_color), (10, 10))
        else:
            self.screen.blit(self.font.render("Training Trial %s"%(trial), True, self.colors['black'], self.bg_color), (10, 10))

        self.font = self.pygame.font.Font(None, 30)

        # Status text about each step
        status = self.env.step_data
        if status:

            # Previous State
            if status['state']:
                self.screen.blit(self.font.render("Previous State: {}".format(status['state']), True, self.colors['white'], self.bg_color), (350, 10))
            if not status['state']:
                self.screen.blit(self.font.render("!! Agent state not updated!", True, self.colors['maroon'], self.bg_color), (350, 10))

            # Action
            if status['violation'] == 0: # Legal
                if status['action'] == None:
                    self.screen.blit(self.font.render("No action taken. (rewarded {:.2f})".format(status['reward']), True, self.colors['dgreen'], self.bg_color), (350, 40))
                else:
                    self.screen.blit(self.font.render("Agent drove {}. (rewarded {:.2f})".format(status['action'], status['reward']), True, self.colors['dgreen'], self.bg_color), (350, 40))
            else: # Illegal
                if status['action'] == None:
                    self.screen.blit(self.font.render("No action taken. (rewarded {:.2f})".format(status['reward']), True, self.colors['maroon'], self.bg_color), (350, 40))
                else:
                    self.screen.blit(self.font.render("{} attempted (rewarded {:.2f})".format(status['action'], status['reward']), True, self.colors['maroon'], self.bg_color), (350, 40))

            # Result
            if status['violation'] == 0: # Legal
                if status['waypoint'] == status['action']: # Followed waypoint
                    self.screen.blit(self.font.render("Agent followed the waypoint!", True, self.colors['dgreen'], self.bg_color), (350, 70))
                elif status['action'] == None:
                    if status['light'] == 'red': # Stuck at a red light
                        self.screen.blit(self.font.render("Agent idled at a red light!", True, self.colors['dgreen'], self.bg_color), (350, 70))
                    else:
                        self.screen.blit(self.font.render("Agent idled at a green light with oncoming traffic.", True, self.colors['mustard'], self.bg_color), (350, 70))
                else: # Did not follow waypoint
                    self.screen.blit(self.font.render("Agent did not follow the waypoint.", True, self.colors['mustard'], self.bg_color), (350, 70))
            else: # Illegal
                if status['violation'] == 1: # Minor violation
                    self.screen.blit(self.font.render("There was a green light with no oncoming traffic.", True, self.colors['maroon'], self.bg_color), (350, 70))
                elif status['violation'] == 2: # Major violation
                    self.screen.blit(self.font.render("There was a red light with no traffic.", True, self.colors['maroon'], self.bg_color), (350, 70))
                elif status['violation'] == 3: # Minor accident
                    self.screen.blit(self.font.render("There was traffic with right-of-way.", True, self.colors['maroon'], self.bg_color), (350, 70))
                elif status['violation'] == 4: # Major accident
                    self.screen.blit(self.font.render("There was a red light with traffic.", True, self.colors['maroon'], self.bg_color), (350, 70))

            # Time Remaining
            if self.env.enforce_deadline:
                time = (status['deadline'] - 1) * 100.0 / (status['t'] + status['deadline'])
                self.screen.blit(self.font.render("{:.0f}% of time remaining to reach destination.".format(time), True, self.colors['black'], self.bg_color), (350, 100))
            else:
                self.screen.blit(self.font.render("Agent not enforced to meet deadline.", True, self.colors['black'], self.bg_color), (350, 100))

            # Denote whether a trial was a success or failure
            if (state['destination'] != state['location'] and state['deadline'] > 0) or (self.env.enforce_deadline is not True and state['destination'] != state['location']):
                self.font = self.pygame.font.Font(None, 40)
                if self.env.success == True:
                    self.screen.blit(self.font.render("Previous Trial: Success", True, self.colors['dgreen'], self.bg_color), (10, 50))
                if self.env.success == False:
                    self.screen.blit(self.font.render("Previous Trial: Failure", True, self.colors['maroon'], self.bg_color), (10, 50))

                if self.env.primary_agent.learning:
                    self.font = self.pygame.font.Font(None, 22)
                    self.screen.blit(self.font.render("epsilon = {:.4f}".format(self.env.primary_agent.epsilon), True, self.colors['black'], self.bg_color), (10, 80))
                    self.screen.blit(self.font.render("alpha = {:.4f}".format(self.env.primary_agent.alpha), True, self.colors['black'], self.bg_color), (10, 95))

        # Reset status text
        else:
            self.pygame.rect.Rect(350, 10, self.width, 200)
            self.font = self.pygame.font.Font(None, 40)
            self.screen.blit(self.font.render("Simulating trial. . .", True, self.colors['white'], self.bg_color), (400, 60))


        # Flip buffers
        self.pygame.display.flip()


    def pause(self):
        """
        When the GUI is enabled, this function will pause the simulation.
        """

        abs_pause_time = time.time()
        self.font = self.pygame.font.Font(None, 30)
        pause_text = "Simulation Paused. Press any key to continue. . ."
        self.screen.blit(self.font.render(pause_text, True, self.colors['red'], self.bg_color), (400, self.height - 30))
        self.pygame.display.flip()
        print pause_text
        while self.paused:
            for event in self.pygame.event.get():
                if event.type == self.pygame.KEYDOWN:
                    self.paused = False
            self.pygame.time.wait(self.frame_delay)
        self.screen.blit(self.font.render(pause_text, True, self.bg_color, self.bg_color), (400, self.height - 30))
        self.start_time += (time.time() - abs_pause_time)

