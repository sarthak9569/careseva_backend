const mongoose = require('mongoose');

const settingsSchema = new mongoose.Schema({
  queue_counter: { type: Number, default: 0 },
  queue_date: { type: String, default: '' },
}, { timestamps: true });

module.exports = mongoose.model('Settings', settingsSchema);