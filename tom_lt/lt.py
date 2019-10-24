import time
import tom_lt.secret

from lxml import etree
from suds import Client
from dateutil.parser import parse
from datetime import datetime

from django import forms
from django.conf import settings

from astropy.coordinates import SkyCoord
from astropy import units as u

from crispy_forms.layout import Layout, Div, HTML
from crispy_forms.bootstrap import PrependedAppendedText, PrependedText, InlineRadios

from tom_observations.facility import GenericObservationForm, GenericObservationFacility
from tom_targets.models import Target

# Determine settings for this module
try:
    LT_SETTINGS = tom_lt.secret.LT_SETTINGS
except (AttributeError, KeyError):
    LT_SETTINGS = {
        'proposalIDs': (('proposal ID','PID1'), ('proposal ID2', 'PID2')),
        'username': 'username',
        'password': 'password'
    }

LT_HOST = '161.72.57.3'
LT_PORT = '8080'
LT_XML_NS = 'http://www.rtml.org/v3.1a'
LT_XSI_NS = 'http://www.w3.org/2001/XMLSchema-instance'
LT_SCHEMA_LOCATION = 'http://www.rtml.org/v3.1a http://telescope.livjm.ac.uk/rtml/RTML-nightly.xsd'

# Print RTML file and do not send to LT
DEBUG = False

class LTObservationForm(GenericObservationForm):
    project = forms.ChoiceField(choices=LT_SETTINGS['proposalIDs'], label='Proposal')
    priority = forms.IntegerField(min_value=1, max_value=3, initial=1)

    startdate = forms.CharField(label='Start Date',
                                widget=forms.TextInput(attrs={'type': 'date'}))
    starttime = forms.CharField(label='Time',
                                widget=forms.TextInput(attrs={'type': 'time'}),
                                initial='12:00')
    enddate = forms.CharField(label='End Date',
                              widget=forms.TextInput(attrs={'type': 'date'}))
    endtime = forms.CharField(label='Time',
                              widget=forms.TextInput(attrs={'type': 'time'}),
                              initial='12:00')

    max_airmass = forms.FloatField(min_value=1, max_value=3, initial=2,
                                   label='Constraints',
                                   widget=forms.NumberInput(attrs={'step': '0.1'}))
    max_seeing = forms.FloatField(min_value=1, max_value=5, initial=1.2,
                                  widget=forms.NumberInput(attrs={'step': '0.1'}),
                                  label='')
    max_skybri = forms.FloatField(min_value=0, max_value=10, initial=1,
                                  widget=forms.NumberInput(attrs={'step': '0.1'}),
                                  label='')
    photometric = forms.ChoiceField(choices=[('clear', 'Yes'), ('light', 'No')], initial='light')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(
            self.common_layout,
            self.layout(),
            self.extra_layout()
        )



    def layout(self):
        return Div(
            Div(
                Div(
                    'project', 'startdate', 'enddate',
                    css_class='col-md-6'
                ),
                Div(
                    'priority', 'starttime', 'endtime',
                    css_class='col-md-6'
                ),
                css_class='form-row'
            ),
            Div(
                Div(css_class='col-md-2'),
                Div(
                    PrependedText('max_airmass', 'Airmass <'),
                    PrependedAppendedText('max_seeing', 'Seeing <', 'arcsec'),
                    PrependedAppendedText('max_skybri', 'SkyBrightness <', 'mag/arcsec'),
                    InlineRadios('photometric'),
                    css_class='col'
                ),
                css_class='form-row'
            ),
            HTML('<hr width="85%"><h4>Instrument Config</h4>'),
            css_class='form-row'
        )

    def extra_layout(self):
        return Div()

    def _build_prolog(self):
        namespaces = {
            'xsi': LT_XSI_NS,
        }
        schemaLocation = etree.QName(LT_XSI_NS, 'schemaLocation')
        uid = 'DJANGO'.format(str(int(time.time())))
        return etree.Element('RTML', {schemaLocation: LT_SCHEMA_LOCATION}, xmlns=LT_XML_NS,
                             mode='request', uid=uid, version='3.1a', nsmap=namespaces)

    def _build_project(self, payload):
        project = etree.Element('Project', ProjectID=self.cleaned_data['project'])
        contact = etree.SubElement(project, 'Contact')
        etree.SubElement(contact, 'Username').text = LT_SETTINGS['username']
        etree.SubElement(contact, 'Name').text = ''
        payload.append(project)

    def _build_constraints(self):
        airmass_const = etree.Element('AirmassConstraint', maximum=str(self.cleaned_data['max_airmass']))

        sky_const = etree.Element('SkyConstraint')
        etree.SubElement(sky_const, 'Flux').text = str(self.cleaned_data['max_skybri'])
        etree.SubElement(sky_const, 'Units').text = 'magnitudes/square-arcsecond'

        seeing_const = etree.Element('SeeingConstraint', maximum=(str(self.cleaned_data['max_seeing'])))

        photom_const = etree.Element('ExtinctionConstraint')
        etree.SubElement(photom_const, 'Clouds').text = self.cleaned_data['photometric']

        date_const = etree.Element('DateTimeConstraint', type='include')
        start = self.cleaned_data['startdate'] + 'T' + self.cleaned_data['starttime'] + ':00+00:00'
        end = self.cleaned_data['enddate'] + 'T' + self.cleaned_data['endtime'] + ':00+00:00'
        etree.SubElement(date_const, 'DateTimeStart', system='UT', value=start)
        etree.SubElement(date_const, 'DateTimeEnd', system='UT', value=end)

        return [airmass_const, sky_const, seeing_const, photom_const, date_const]

    def _build_target(self):
        target_to_observe = Target.objects.get(pk=self.cleaned_data['target_id'])

        target = etree.Element('Target', name=target_to_observe.name)
        c = SkyCoord(ra=target_to_observe.ra*u.degree, dec=target_to_observe.dec*u.degree)
        coordinates = etree.SubElement(target, 'Coordinates')
        ra = etree.SubElement(coordinates, 'RightAscension')
        etree.SubElement(ra, 'Hours').text = str(int(c.ra.hms.h))
        etree.SubElement(ra, 'Minutes').text = str(int(c.ra.hms.m))
        etree.SubElement(ra, 'Seconds').text = str(c.ra.hms.s)

        dec = etree.SubElement(coordinates, 'Declination')
        sign = '+' if c.dec.signed_dms.sign == '1.0' else '-'
        etree.SubElement(dec, 'Degrees').text = sign + str(int(c.dec.signed_dms.d))
        etree.SubElement(dec, 'Arcminutes').text = str(int(c.dec.signed_dms.m))
        etree.SubElement(dec, 'Arcseconds').text = str(c.dec.signed_dms.s)
        etree.SubElement(coordinates, 'Equinox').text = target_to_observe.epoch
        return target

    def observation_payload(self):
        payload = self._build_prolog()
        self._build_project(payload)
        self._build_inst_schedule(payload)
        if(DEBUG == True):
            f = open("django.RTML", "w")
            f.write(etree.tostring(payload, encoding="unicode", pretty_print=True))
            f.close()
        return etree.tostring(payload, encoding="unicode")


class LT_IOO_ObservationForm(LTObservationForm):
    binning = forms.ChoiceField(choices=[('1x1', '1x1'), ('2x2', '2x2')], initial=('2x2', '2x2'), help_text='2x2 binning is usual, giving 0.3 arcsec/pixel, faster readout and lower readout noise. 1x1 binning should only be selected if specifically required.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters = ('U',
                        'R',
                        'G',
                        'I',
                        'Z',
                        'B',
                        'V',
                        'Halpha6566',
                        'Halpha6634',
                        'Halpha6705',
                        'Halpha6755',
                        'Halpha6822')

        for filter in self.filters:
            if filter == self.filters[0]:
                self.fields['exposure_time_' + filter] = forms.FloatField(min_value=0,
                                                                          initial=120,
                                                                          label='Integration Time')
                self.fields['exposure_count_' + filter] = forms.IntegerField(min_value=0,
                                                                             initial=0,
                                                                             label='No. of integrations')
            else:
                self.fields['exposure_time_' + filter] = forms.FloatField(min_value=0,
                                                                          initial=120,
                                                                          label='')
                self.fields['exposure_count_' + filter] = forms.IntegerField(min_value=0,
                                                                             initial=0,
                                                                             label='')

    def extra_layout(self):
        return Div(
            Div(
                Div(HTML('<br><h5>Sloan</h5>'), css_class='form_row'),
                Div(
                    Div(PrependedAppendedText('exposure_time_U', 'u\'', 's'),
                        PrependedAppendedText('exposure_time_G', 'g\'', 's'),
                        PrependedAppendedText('exposure_time_R', 'r\'', 's'),
                        PrependedAppendedText('exposure_time_I', 'i\'', 's'),
                        PrependedAppendedText('exposure_time_Z', 'z\'', 's'),
                        css_class='col-md-6', ),

                    Div('exposure_count_U',
                        'exposure_count_G',
                        'exposure_count_R',
                        'exposure_count_I',
                        'exposure_count_Z',
                        css_class='col-md-6'),
                    css_class='form-row'
                ),
                Div(HTML('<br><h5>Bessell</h5>'), css_class='form_row'),
                Div(
                    Div(PrependedAppendedText('exposure_time_B', 'B', 's'),
                        PrependedAppendedText('exposure_time_V', 'V', 's'),
                        css_class='col-md-6', ),

                    Div('exposure_count_B',
                        'exposure_count_V',
                        css_class='col-md-6'),
                    css_class='form-row'
                ),
                Div(HTML('<br><h5>H-alpha</h5>'), css_class='form_row'),

                Div(
                    Div(PrependedAppendedText('exposure_time_Halpha6566', '6566', 's'),
                        PrependedAppendedText('exposure_time_Halpha6634', '6634', 's'),
                        PrependedAppendedText('exposure_time_Halpha6705', '6705', 's'),
                        PrependedAppendedText('exposure_time_Halpha6755', '6755', 's'),
                        PrependedAppendedText('exposure_time_Halpha6822', '6822', 's'),
                        css_class='col-md-6', ),

                    Div('exposure_count_Halpha6566',
                        'exposure_count_Halpha6634',
                        'exposure_count_Halpha6705',
                        'exposure_count_Halpha6755',
                        'exposure_count_Halpha6822',
                        css_class='col-md-6'),
                    css_class='form-row'
                    ),
                css_class='col'
            ),
            Div(css_class='col-md-1'),
            Div(
                Div('binning', css_class='col'),
                css_class='col'
            ),
            css_class='form-row'
        )

    def _build_inst_schedule(self, payload):

        for filter in self.filters:
            if self.cleaned_data['exposure_count_' + filter] != 0:
                payload.append(self._build_schedule(filter))

    def _build_schedule(self, filter):
        exposure_time = self.cleaned_data['exposure_time_' + filter]
        exposure_count = self.cleaned_data['exposure_count_' + filter]

        schedule = etree.Element('Schedule')
        device = etree.SubElement(schedule, 'Device', name="IO:O", type="camera")
        etree.SubElement(device, 'SpectralRegion').text = 'optical'
        setup = etree.SubElement(device, 'Setup')
        etree.SubElement(setup, 'Filter', type=filter)
        detector = etree.SubElement(setup, 'Detector')
        binning = etree.SubElement(detector, 'Binning')
        etree.SubElement(binning, 'X', units='pixels').text = self.cleaned_data['binning'].split('x')[0]
        etree.SubElement(binning, 'Y', units='pixels').text = self.cleaned_data['binning'].split('x')[1]
        exposure = etree.SubElement(schedule, 'Exposure', count=str(exposure_count))
        etree.SubElement(exposure, 'Value', units='seconds').text = str(exposure_time)
        schedule.append(self._build_target())
        for const in self._build_constraints():
            schedule.append(const)
        return schedule



class LT_IOI_ObservationForm(LTObservationForm):
    exposure_time = forms.FloatField(min_value=0, initial=120, label='Integration time',
                                       widget=forms.NumberInput(attrs={'step': '0.1'}))
    exposure_count = forms.IntegerField(min_value=1, initial=1, label='No. of integrations', help_text='The Liverpool Telescope will automatically create a dither pattern between exposures.')

    def extra_layout(self):
        return Div(
            Div(
                Div(
                    Div(PrependedAppendedText('exposure_time', 'H', 's'), css_class='col-md-6'),
                    Div('exposure_count', css_class='col-md-6'),
                    css_class='form-row'
                ),
                css_class='col'
            ),
            Div(css_class='col-md-1'),
            Div(css_class='col'),
            css_class='form-row'
        )
    def _build_inst_schedule(self, payload):
        exposure_time = self.cleaned_data['exposure_time_' + filter]
        exposure_count = self.cleaned_data['exposure_count_' + filter]

        schedule = etree.Element('Schedule')
        device = etree.SubElement(schedule, 'Device', name="IO:I", type="camera")
        etree.SubElement(device, 'SpectralRegion').text = 'optical'
        setup = etree.SubElement(device, 'Setup')
        etree.SubElement(setup, 'Filter', type='H')
        detector = etree.SubElement(setup, 'Detector')
        binning = etree.SubElement(detector, 'Binning')
        etree.SubElement(binning, 'X', units='pixels').text = '1'
        etree.SubElement(binning, 'Y', units='pixels').text = '1'
        exposure = etree.SubElement(schedule, 'Exposure', count=str(exposure_count))
        etree.SubElement(exposure, 'Value', units='seconds').text = str(exposure_time)
        schedule.append(self._build_target())
        for const in self._build_constraints():
            schedule.append(const)
        payload.append(schedule)


class LT_SPRAT_ObservationForm(LTObservationForm):
    exposure_time = forms.FloatField(min_value=0, initial=120, label='Integration time',
                                       widget=forms.NumberInput(attrs={'step': '0.1'}))
    exposure_count = forms.IntegerField(min_value=1, initial=1, label='No. of integrations')

    grating = forms.ChoiceField(choices=[('red', 'Red'), ('blue', 'Blue')], initial='red')

    def extra_layout(self):
        return Div(
            Div(
                Div(
                    Div(PrependedAppendedText('exposure_time', '', 's'), css_class='col-md-6'),
                    Div('exposure_count', css_class='col-md-6'),
                    css_class='form-row'
                ),
                css_class='col'
            ),
            Div(css_class='col-md-1'),
            Div(
                Div('grating', css_class='col'),
                css_class='col'
            ),
            css_class='form-row'
        )


    def _build_inst_schedule(self, payload):
        exposure_time = self.cleaned_data['exposure_time_' + filter]
        exposure_count = self.cleaned_data['exposure_count_' + filter]

        schedule = etree.Element('Schedule')
        device = etree.SubElement(schedule, 'Device', name="IO:I", type="camera")
        etree.SubElement(device, 'SpectralRegion').text = 'optical'
        setup = etree.SubElement(device, 'Setup')
        etree.SubElement(setup, 'Filter', type='H')
        detector = etree.SubElement(setup, 'Detector')
        binning = etree.SubElement(detector, 'Binning')
        etree.SubElement(binning, 'X', units='pixels').text = '1'
        etree.SubElement(binning, 'Y', units='pixels').text = '1'
        exposure = etree.SubElement(schedule, 'Exposure', count=str(exposure_count))
        etree.SubElement(exposure, 'Value', units='seconds').text = str(exposure_time)
        schedule.append(self._build_target())
        for const in self._build_constraints():
            schedule.append(const)
        payload.append(schedule)


class LT_FRODO_ObservationForm(LTObservationForm):
    exposure_time_high = forms.FloatField(min_value=0, initial=120, label='Integration time',
                                     widget=forms.NumberInput(attrs={'step': '0.1'}))
    exposure_count_high = forms.IntegerField(min_value=0, initial=0, label='No. of integrations')

    exposure_time_low = forms.FloatField(min_value=0, initial=120, label='',
                                     widget=forms.NumberInput(attrs={'step': '0.1'}))
    exposure_count_low = forms.IntegerField(min_value=0, initial=0, label='')

    grating = forms.ChoiceField(choices=[('red', 'Red'), ('blue', 'Blue')], initial='red')


    def extra_layout(self):
        return Div(
            Div(
                Div(
                    Div(PrependedAppendedText('exposure_time_high', 'High Res', 's'), PrependedAppendedText('exposure_time_low', 'Low Res', 's'), css_class='col-md-6'),
                    Div('exposure_count_high', 'exposure_count_low', css_class='col-md-6'),
                    css_class='form-row'
                ),
                css_class='col'
            ),
            Div(css_class='col-md-1'),
            Div(
                Div('grating', css_class='col'),
                css_class='col'
            ),
            css_class='form-row'
        )

    def _build_inst_schedule(self, payload):
        for device in ('FrodoSpec-Blue', 'FrodoSpec-Red'):
            payload.append(self._build_schedule(device))

    def _build_schedule(self, device):
        schedule = etree.Element('Schedule')
        device = etree.SubElement(schedule, 'Device', name="IO:I", type="camera")
        etree.SubElement(device, 'SpectralRegion').text = 'optical'
        setup = etree.SubElement(device, 'Setup')
        etree.SubElement(setup, 'Filter', type='H')
        detector = etree.SubElement(setup, 'Detector')
        binning = etree.SubElement(detector, 'Binning')
        etree.SubElement(binning, 'X', units='pixels').text = '1'
        etree.SubElement(binning, 'Y', units='pixels').text = '1'
        exposure = etree.SubElement(schedule, 'Exposure', count=str(self.cleaned_data['exposure_count']))
        etree.SubElement(exposure, 'Value', units='seconds').text = str(self.cleaned_data['exposure_time'])
        schedule.append(self._build_target())
        for const in self._build_constraints():
            schedule.append(const)
        return schedule


class LTFacility(GenericObservationFacility):
    name = 'LT'
    observation_types = [('IOO', 'IO:O'), ('IOI', 'IO:I'), ('SPRAT', 'Sprat'), ('FRODO', 'Frodo')]

    SITES = {
            'La Palma': {
                'sitecode': 'orm',
                'latitude': 28.762,
                'longitude': -17.872,
                'elevation': 2363}
            }

    def get_form(self, observation_type):
        if observation_type == 'IOO':
            return LT_IOO_ObservationForm
        elif observation_type == 'IOI':
            return LT_IOI_ObservationForm
        elif observation_type == 'SPRAT':
            return LT_SPRAT_ObservationForm
        elif observation_type == 'FRODO':
            return LT_FRODO_ObservationForm
        else:
            return LT_IOO_ObservationForm

    def submit_observation(self, observation_payload):
        if (DEBUG == False):
            headers = {
                'Username': LT_SETTINGS['username'],
                'Password': LT_SETTINGS['password']
            }
            url = '{0}://{1}:{2}/node_agent2/node_agent?wsdl'.format('http', LT_HOST, LT_PORT)
            client = Client(url=url, headers=headers)
            response = client.service.handle_rtml(observation_payload)
            response_rtml = etree.fromstring(response)
            obs_id = response_rtml.get('uid').split('-')[-1]
            return [0]
        else:
            return[0]

    def cancel_observation(self, observation_id):
        form = self.get_form()()
        payload = form._build_prolog()
        payload.append(form._build_project())

    def validate_observation(self, observation_payload):
        return

    def get_observation_url(self, observation_id):
        return ''

    def get_terminal_observing_states(self):
        return ['IN_PROGRESS', 'COMPLETED']

    def get_observing_sites(self):
        return self.SITES

    def get_observation_status(self, observation_id):
        return

    def data_products(self, observation_id, product_id=None):
        return []
