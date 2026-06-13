import mongoose from "mongoose";
import { MongoMemoryServer } from "mongodb-memory-server";

/**
 * Global is used here to maintain a cached connection across hot reloads
 * in development. We use mongodb-memory-server to run a completely local,
 * zero-setup in-memory database.
 */
let cached = global.mongoose;

if (!cached) {
  cached = global.mongoose = { conn: null, promise: null, mongoServer: null };
}

async function connectDB() {
  if (cached.conn) {
    return cached.conn;
  }

  if (!cached.promise) {
    const opts = {
      bufferCommands: false,
    };

    cached.promise = (async () => {
      console.log("Starting local in-memory MongoDB server...");
      const mongoServer = await MongoMemoryServer.create({
        instance: {
          dbName: "breakpoint"
        }
      });
      cached.mongoServer = mongoServer;
      const uri = mongoServer.getUri();
      console.log("🚀 In-memory MongoDB Server running at:", uri);
      
      const conn = await mongoose.connect(uri, opts);
      console.log("✅ Connected successfully to local in-memory MongoDB database.");
      return conn;
    })();
  }

  try {
    cached.conn = await cached.promise;
  } catch (e) {
    cached.promise = null;
    throw e;
  }

  return cached.conn;
}

export default connectDB;
