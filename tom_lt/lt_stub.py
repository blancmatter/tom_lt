from tom_observations.facility import GenericObservationForm, GenericObservationFacility

from crispy_forms.layout import Layout, HTML

class LTObservationForm(GenericObservationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.inputs.pop()
        self.helper.layout = Layout(
            HTML('''
                <p>
                This plugin is a stub for the Liverpool Telescope plugin. In order to install the full plugin, please see the
                instructions <a href="https://github.com/TOMToolkit/tom_lt">here</a>.
                </p>
            '''),
            HTML('''<a class="btn btn-outline-primary" href={% url 'tom_targets:list' %}>Back</a>''')
        )

class LTFacility(GenericObservationFacility):
    name = 'LTStub'
    observation_types = [('LTStub', 'LtStub'),]

    def get_form(self, observation_type):
        return LTObservationForm

    SITES = {
            'La Palma': {
                'sitecode': 'orm',
                'latitude': 28.762,
                'longitude': -17.872,
                'elevation': 2363}
            }

    def submit_observation(self, observation_payload):
            return [obs_id]

    def cancel_observation(self, observation_id):
        pass

    def validate_observation(self, observation_payload):
        return []

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
