import java.util.Scanner;

public class KadaneMaxSubarray {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        if (n > 100) n = 100;
        int[] a = new int[n];
        for (int i = 0; i < n; ++i) {
            a[i] = scanner.nextInt();
        }
        int maxEnding = a[0], maxSoFar = a[0];
        for (int i = 1; i < n; ++i) {
            if (maxEnding < 0) maxEnding = a[i]; else maxEnding += a[i];
            if (maxEnding > maxSoFar) maxSoFar = maxEnding;
        }
        System.out.println("Max subarray sum: " + maxSoFar);
    }
}