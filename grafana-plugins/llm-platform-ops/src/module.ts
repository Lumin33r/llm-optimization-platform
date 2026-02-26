import { PanelPlugin } from '@grafana/data';
import { OpsPanel } from './components/OpsPanel';

export const plugin = new PanelPlugin(OpsPanel).setPanelOptions((builder) => {
  builder
    .addTextInput({
      path: 'gatewayUrl',
      name: 'Gateway URL',
      description: 'Base URL for the LLM Platform Gateway ops API',
      defaultValue: 'http://gateway.platform.svc.cluster.local',
    })
    .addNumberInput({
      path: 'refreshInterval',
      name: 'Refresh Interval (seconds)',
      description: 'How often to poll for updated data',
      defaultValue: 30,
    });
});
