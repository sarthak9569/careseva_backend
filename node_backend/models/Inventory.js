const mongoose = require('mongoose');

const inventorySchema = new mongoose.Schema({
  hospital: { type: mongoose.Schema.Types.ObjectId, ref: 'Hospital', required: true },
  itemName: { type: String, required: true },
  category: { type: String, enum: ['Medicine', 'Equipment', 'Consumable'] },
  quantity: { type: Number, default: 0 },
  unit: String,
  expiryDate: Date,
  batchNumber: String,
  purchaseDetails: {
    vendor: String,
    date: Date,
    price: Number
  }
}, { timestamps: true });

module.exports = mongoose.model('Inventory', inventorySchema);
