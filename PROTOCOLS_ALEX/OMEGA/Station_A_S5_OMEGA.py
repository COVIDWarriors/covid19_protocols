from opentrons import protocol_api
from opentrons.drivers.rpi_drivers import gpio
import time
import json
import math
import os

# metadata
metadata = {
    'protocolName': 'S5 Station A Version 1',
    'author': 'Nick <protocols@opentrons.com> & Alex Gasulla',
    'source': 'Custom Protocol Request',
    'apiLevel': '2.0'
}

NUM_SAMPLES     = 23
SAMPLE_VOLUME   = 200
TNA_VOLUME      = 240
ISO_VOLUME      = 280
BEADS_VOLUME    = 10
TIP_TRACK       = False
recycle_tips    = False

def run(ctx: protocol_api.ProtocolContext):
    #Change light to red
    gpio.set_button_light(1,0,0)

    # load labware
    source_racks = [
        ctx.load_labware(
            'opentrons_24_tuberack_generic_2ml_screwcap', slot,
            'source tuberack ' + str(i+1))
        for i, slot in enumerate(['4', '1', '6', '3'])
    ]
    dest_plate = ctx.load_labware(
        'usascientific_96_wellplate_2.4ml_deep', '2',
        '96-deepwell sample plate')
    reagent_rack = ctx.load_labware('opentrons_6_tuberack_falcon_50ml_conical',
                                     '5', 'lysis buffer tuberack')

    tipracks1000 = [ctx.load_labware('opentrons_96_filtertiprack_1000ul', slot,
                                     '1000µl filter tiprack')
                    for slot in ['8']]

    # load pipette
    p1000 = ctx.load_instrument(
        'p1000_single_gen2', 'right', tip_racks=tipracks1000)

    # setup samples
    sources = [
        well for rack in source_racks for rack_rows in rack.rows() for well in rack_rows][:NUM_SAMPLES]
    '''sources = [
        well for rack in source_racks for well in rack.wells()][:NUM_SAMPLES]'''
    dests = dest_plate.wells()[:NUM_SAMPLES]

    tip_log = {}
    tip_file_path = '/data/A/tip_log.json'
    if tip_log and not ctx.is_simulating():
        if os.path.isfile(tip_file_path):
            with open(tip_file_path) as json_file:
                data = json.load(json_file)
                if 'tips1000' in data:
                    tip_log['count'] = {p1000: data['tips1000']}
                else:
                    tip_log['count'] = {p1000: 0}
    else:
        tip_log['count'] = {p1000: 0}

    tip_log['tips'] = {
        p1000: [tip for rack in tipracks1000 for tip in rack.wells()]}
    tip_log['max'] = {p1000: len(tip_log['tips'][p1000])}

    def pick_up(pip):
        nonlocal tip_log
        if tip_log['count'][pip] == tip_log['max'][pip]:
            ctx.pause('Replace ' + str(pip.max_volume) + 'µl tipracks before \
    resuming.')
            pip.reset_tipracks()
            tip_log['count'][pip] = 0
        pip.pick_up_tip(tip_log['tips'][pip][tip_log['count'][pip]])
        tip_log['count'][pip] += 1

    lys_buff = reagent_rack.wells()[:1]
    heights = {tube: 60 for tube in lys_buff}
    radius = (lys_buff[0].diameter)/2
    min_h = 16

    def calc_height(tube, vol):
        nonlocal heights
        dh = vol / (math.pi * (radius**2))
        if heights[tube] - dh > min_h:
            heights[tube] = heights[tube] - dh
        else:
            heights[tube] = 1
        return tube.bottom(heights[tube])

    def move_vol_multi(pipet, reagent, source, dest, vol, x_offset, pickup_height, rinse, wait_time, blow_out):
        # Rinse before aspirating
        if rinse == True:
            #pipet.aspirate(air_gap_vol_top, location = source.top(z = -5), rate = reagent.flow_rate_aspirate) #air gap
            custom_mix(pipet, reagent, location = source, vol = vol, rounds = 10, blow_out = False, mix_height = 0)
            #pipet.dispense(air_gap_vol_top, location = source.top(z = -5), rate = reagent.flow_rate_dispense)

        # SOURCE
        if reagent.air_gap_vol_top != 0: #If there is air_gap_vol, switch pipette to slow speed
            pipet.move_to(source.top(z = 0))
            pipet.air_gap(reagent.air_gap_vol_top) #air gap
            #pipet.aspirate(reagent.air_gap_vol_top, source.top(z = -5), rate = reagent.flow_rate_aspirate) #air gap

        s = source.bottom(pickup_height).move(Point(x = x_offset))
        pipet.aspirate(vol, s) # aspirate liquid

        if reagent.air_gap_vol_bottom != 0: #If there is air_gap_vol, switch pipette to slow speed
            pipet.move_to(source.top(z = 0))
            pipet.air_gap(reagent.air_gap_vol_bottom) #air gap
            #pipet.aspirate(air_gap_vol_bottom, source.top(z = -5), rate = reagent.flow_rate_aspirate) #air gap

        if wait_time != 0:
            ctx.delay(seconds=wait_time, msg='Waiting for ' + str(wait_time) + ' seconds.')

        # GO TO DESTINATION
        pipet.dispense(vol - reagent.disposal_volume + reagent.air_gap_vol_bottom, dest.top(z = -5), rate = reagent.flow_rate_dispense)

        if wait_time != 0:
            ctx.delay(seconds=wait_time, msg='Waiting for ' + str(wait_time) + ' seconds.')

        if reagent.air_gap_vol_top != 0:
            pipet.dispense(reagent.air_gap_vol_top, dest.top(z = 0), rate = reagent.flow_rate_dispense)

        if blow_out == True:
            pipet.blow_out(dest.top(z = 0))

    # transfer TNA
    pick_up(p1000)
    source = lys_buff[0]
    for i, d in enumerate(dests):
        p1000.transfer(TNA_VOLUME + ISO_VOLUME + BEADS_VOLUME, source.bottom(1), d.bottom(2),
                      new_tip='never')
        p1000.mix(2, SAMPLE_VOLUME, d.bottom(2))
        p1000.blow_out(d.top(-5)) # Blow out carried out at fixed arbitrary heigth

    if recycle_tips == True:
        p1000.return_tip()
    else:
        p1000.drop_tip(home_after=False)

    # transfer samples
    for s, d in zip(sources, dests):
        #print(sources)
        #print(s)
        if not p1000.hw_pipette['has_tip']:
            pick_up(p1000)
        #p1000.transfer(SAMPLE_VOLUME, s.bottom(0.5), d.bottom(5), new_tip='never')
        #p1000.aspirate(100, d.top())
        if recycle_tips == True:
            p1000.return_tip()
        else:
            p1000.drop_tip(home_after=False)

    # track final used tip
    if not ctx.is_simulating():
        if not os.path.isdir('/data/A'):
            os.mkdir('/data/A')
        data = {'tips1000': tip_log['count'][p1000]}
        with open(tip_file_path, 'w') as outfile:
            json.dump(data, outfile)

    # Send robot home
    ctx.comment(' ')
    ctx.comment('###############################################')
    ctx.comment('Homing robot')
    ctx.comment('###############################################')
    ctx.comment(' ')
    ctx.home()
###############################################################################
    # Light flash end of program
    #import os
    #os.system('mpg123 /etc/audio/speaker-test.mp3')
    for i in range(3):
        gpio.set_rail_lights(False)
        gpio.set_button_light(1,0,0)
        time.sleep(0.3)
        gpio.set_rail_lights(True)
        gpio.set_button_light(0,0,1)
        time.sleep(0.3)
    gpio.set_button_light(0,1,0)
    ctx.comment('Finished!')
