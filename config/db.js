const mongoose = require('mongoose');

/**
 * Connects to MongoDB. Call once before handling HTTP traffic so queries never sit in Mongoose's buffer.
 */
async function connectDB() {
  const uri = process.env.MONGODB_URI?.trim();

  if (!uri || !uri.startsWith('mongodb')) {
    console.error('\n[x] Set MONGODB_URI in backend/.env to your MongoDB Atlas connection string (mongodb+srv://...).\n');
    process.exit(1);
  }

  mongoose.set('bufferCommands', false);

  try {
    const conn = await mongoose.connect(uri, {
      serverSelectionTimeoutMS: 15000,
    });
    console.log(`CareQueue database connected: ${conn.connection.host}`);
  } catch (error) {
    console.error('\n[x] MongoDB connection failed:', error.message);
    console.error('    Atlas → Network Access: allow your current IP, or 0.0.0.0/0 for local dev.');
    console.error('    Confirm database user/password and cluster hostname in MONGODB_URI.\n');
    process.exit(1);
  }
}

module.exports = connectDB;
