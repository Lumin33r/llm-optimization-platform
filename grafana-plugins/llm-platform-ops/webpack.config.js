const path = require('path');

module.exports = {
  entry: './src/module.ts',
  output: {
    filename: 'module.js',
    path: path.resolve(__dirname, 'dist'),
    library: {
      type: 'amd',
    },
    clean: true,
  },
  externals: [
    'react',
    'react-dom',
    '@grafana/data',
    '@grafana/ui',
    '@grafana/runtime',
  ],
  resolve: {
    extensions: ['.ts', '.tsx', '.js', '.jsx'],
  },
  module: {
    rules: [
      {
        test: /\.tsx?$/,
        use: 'ts-loader',
        exclude: /node_modules/,
      },
      {
        test: /\.css$/,
        use: ['style-loader', 'css-loader'],
      },
    ],
  },
};
