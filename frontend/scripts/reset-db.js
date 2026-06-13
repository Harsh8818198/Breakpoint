import mongoose from 'mongoose';

const MONGODB_URI = process.env.MONGODB_URI;

if (!MONGODB_URI) {
  console.error('❌ MONGODB_URI is not defined in .env.local');
  process.exit(1);
}

async function resetDB() {
  try {
    console.log('⏳ Connecting to MongoDB...');
    await mongoose.connect(MONGODB_URI);
    console.log('✅ Connected.');

    const collections = await mongoose.connection.db.collections();
    
    for (let collection of collections) {
      console.log(`🧹 Dropping collection: ${collection.collectionName}`);
      await collection.drop();
    }

    console.log('✨ All collections dropped. Database is clean.');
  } catch (error) {
    console.error('❌ Error resetting database:', error);
  } finally {
    await mongoose.disconnect();
    console.log('👋 Disconnected from MongoDB.');
  }
}

resetDB();
