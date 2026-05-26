import java.util.Scanner;

public class ArmstrongNumbers {
    public static boolean isArmstrong(int x) {
        int original = x, sum = 0;
        int digits = 0, t = x;
        while (t > 0) { 
            digits++; 
            t /= 10; 
        }
        t = x;
        while (t > 0) {
            int d = t % 10;
            int p = (int) Math.pow(d, digits);
            sum += p;
            t /= 10;
        }
        return sum == original;
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        for (int i = 0; i < n; ++i) {
            int v = scanner.nextInt();
            System.out.println(v + " -> " + (isArmstrong(v) ? "ARMSTRONG" : "NOT"));
        }
        scanner.close();
    }
}